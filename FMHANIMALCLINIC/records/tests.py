import json
import os
import tempfile
from datetime import date, time
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.activity_signals import log_medical_record_changes
from accounts.models import ActivityLog
from accounts.rbac_models import Module, ModulePermission, Role
from appointments.models import Appointment
from branches.models import Branch
from diagnostics.models import AIDiagnosis
from employees.models import StaffMember
from patients.models import Pet
from settings.models import ClinicalStatus
from .models import MedicalFile, MedicalRecord, RecordEntry
from .models import validate_laboratory_image, validate_medical_file
from .views import (
    _get_pdf_styles,
    _pdf_link_callback,
    get_record_pdf_blocking_fields,
)
from settings.forms import MedicalRecordsSettingsForm


class MedicalRecordOwnerEmailDisplayTests(TestCase):
    def test_portal_patient_displays_email_from_linked_account(self):
        owner = get_user_model().objects.create_user(
            username='record-email-owner',
            email='portal-owner@example.com',
            password='A-secure-test-password-923!',
        )
        pet = Pet.objects.create(
            owner=owner,
            name='Portal Email Patient',
            species='Dog',
            sex=Pet.Sex.FEMALE,
        )

        self.assertEqual(pet.owner_display_email, 'portal-owner@example.com')

    def test_walkin_patient_displays_email_from_guest_contact_details(self):
        pet = Pet.objects.create(
            source=Pet.Source.WALKIN,
            guest_owner_name='Walk-in Owner',
            guest_owner_email='walkin-owner@example.com',
            name='Walk-in Email Patient',
            species='Dog',
            sex=Pet.Sex.FEMALE,
        )

        self.assertEqual(pet.owner_display_email, 'walkin-owner@example.com')


class ArchiveSoftDeleteTests(TestCase):
    def setUp(self):
        self.pet = Pet.objects.create(
            name='Archived Patient',
            species='Dog',
            sex=Pet.Sex.FEMALE,
        )
        self.record = MedicalRecord.objects.create(
            pet=self.pet,
            date_recorded='2026-10-13',
        )
        self.entry = RecordEntry.objects.create(
            record=self.record,
            date_recorded='2026-10-13',
        )

    def test_deleting_pet_archives_pet_record_and_visit_history(self):
        self.pet.delete()

        self.pet.refresh_from_db()
        self.record.refresh_from_db()
        self.entry.refresh_from_db()
        self.assertTrue(self.pet.is_deleted)
        self.assertFalse(self.pet.is_active)
        self.assertTrue(self.record.is_deleted)
        self.assertTrue(self.entry.is_deleted)
        self.assertFalse(Pet.objects.filter(pk=self.pet.pk).exists())
        self.assertFalse(MedicalRecord.objects.filter(pk=self.record.pk).exists())
        self.assertTrue(Pet.all_objects.filter(pk=self.pet.pk).exists())

    def test_restoring_pet_restores_history_archived_with_it(self):
        self.pet.delete()
        self.pet.restore()

        self.pet.refresh_from_db()
        self.record.refresh_from_db()
        self.entry.refresh_from_db()
        self.assertTrue(self.pet.is_active)
        self.assertFalse(self.pet.is_deleted)
        self.assertFalse(self.record.is_deleted)
        self.assertFalse(self.entry.is_deleted)

    def test_deleting_medical_record_archives_its_visit_entries(self):
        self.record.delete()

        self.record.refresh_from_db()
        self.entry.refresh_from_db()
        self.assertTrue(self.record.is_deleted)
        self.assertTrue(self.entry.is_deleted)
        self.assertFalse(RecordEntry.objects.filter(pk=self.entry.pk).exists())
        self.assertTrue(RecordEntry.all_objects.filter(pk=self.entry.pk).exists())

    def test_archiving_medical_record_deletes_linked_ai_diagnosis(self):
        diagnosis = AIDiagnosis.objects.create(
            pet=self.pet,
            primary_condition='Test diagnosis',
            linked_record_entry=self.entry,
        )

        self.record.delete()

        self.assertFalse(AIDiagnosis.objects.filter(pk=diagnosis.pk).exists())
        self.assertTrue(RecordEntry.all_objects.filter(pk=self.entry.pk).exists())

    def test_deleting_ai_diagnosis_preserves_medical_record_and_entry(self):
        diagnosis = AIDiagnosis.objects.create(
            pet=self.pet,
            primary_condition='Test diagnosis',
            linked_record_entry=self.entry,
        )

        diagnosis.delete()

        self.record.refresh_from_db()
        self.entry.refresh_from_db()
        self.assertFalse(self.record.is_deleted)
        self.assertFalse(self.entry.is_deleted)
        self.assertTrue(RecordEntry.objects.filter(pk=self.entry.pk).exists())


class MedicalRecordActivitySignalTests(SimpleTestCase):
    @patch('accounts.activity_signals.log_activity')
    def test_creation_logs_current_clinical_signs_field(self, log_activity):
        instance = SimpleNamespace(
            _user=object(),
            _ip_address=None,
            id=1,
            pet=SimpleNamespace(name='Carl'),
            history_clinical_signs='Limping',
        )

        log_medical_record_changes(MedicalRecord, instance, created=True)

        self.assertEqual(
            log_activity.call_args.kwargs['details'],
            'History / Clinical Signs: Limping',
        )
        self.assertEqual(
            log_activity.call_args.kwargs['category'], ActivityLog.Category.MEDICAL,
        )


class BranchRestrictedMedicalRecordListTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name='Medical Record Scope Branch',
            phone_number='09123456789',
            address='1 Test Street',
            city='Test City',
            state='Test State',
            zip_code='1000',
        )
        module, _ = Module.objects.get_or_create(
            code='medical_records', defaults={'name': 'Medical Records'},
        )
        role = Role.objects.create(
            name='Medical Record Scope Role',
            code='medical-record-scope-test-role',
            hierarchy_level=2,
        )
        ModulePermission.objects.create(
            role=role,
            module=module,
            permission_type=ModulePermission.PermissionType.VIEW,
            restrict_to_branch=True,
        )
        self.user = get_user_model().objects.create_user(
            username='medical-record-scope-user', assigned_role=role,
        )
        self.pet = Pet.objects.create(
            name='Record Scope Pet', species='Cat', sex=Pet.Sex.FEMALE,
        )
        MedicalRecord.objects.create(
            pet=self.pet,
            branch=self.branch,
            date_recorded='2026-10-12',
        )

    def test_unassigned_branch_restricted_staff_cannot_see_medical_records(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('records:admin_list'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['branch_assignment_required'])
        self.assertEqual(response.context['records'].paginator.count, 0)
        self.assertContains(response, 'Ask an administrator to assign your branch')


@override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }
)
class AttendingVeterinarianDefaultTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name='Attending Vet Default Branch')
        role, _ = Role.objects.get_or_create(
            code='veterinarian',
            defaults={
                'name': 'Veterinarian',
                'hierarchy_level': 3,
                'is_staff_role': True,
            },
        )
        module, _ = Module.objects.get_or_create(
            code='medical_records',
            defaults={'name': 'Medical Records'},
        )
        ModulePermission.objects.get_or_create(
            role=role,
            module=module,
            permission_type=ModulePermission.PermissionType.CREATE,
        )
        ModulePermission.objects.get_or_create(
            role=role,
            module=module,
            permission_type=ModulePermission.PermissionType.EDIT,
        )
        self.user = get_user_model().objects.create_user(
            username='attending-vet-default',
            email='attending-vet-default@example.com',
            password='A-secure-test-password-923!',
            assigned_role=role,
            branch=self.branch,
        )
        self.vet = StaffMember.objects.create(
            user=self.user,
            first_name='Attending',
            last_name='Veterinarian',
            position=StaffMember.Position.VETERINARIAN,
            branch=self.branch,
        )
        self.client.force_login(self.user)

    def test_new_visit_entry_defaults_to_logged_in_veterinarian(self):
        response = self.client.get(reverse('records:admin_create'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form']['vet'].value(), self.vet.pk)
        self.assertEqual(response.context['service_branch_id'], self.branch.pk)
        self.assertEqual(response.context['selected_branch_id'], str(self.branch.pk))
        self.assertContains(response, 'petData.branch_id && !serviceBranchId')
        self.assertContains(response, 'name="selected_pet_id"')
        self.assertContains(response, 'This pet is already registered for this owner.')
        self.assertContains(response, 'A guest owner with this name has different phone or email details.')
        self.assertContains(response, 'result.same_guest ? null : result')
        self.assertContains(response, 'name="selected_guest_owner"')
        self.assertContains(response, "result.addEventListener('mousedown'")
        self.assertContains(response, 'name="owner_email"')

    def test_create_form_keeps_same_name_guests_separate_by_contact_details(self):
        first_pet = Pet.objects.create(
            name='Milo',
            source=Pet.Source.WALKIN,
            guest_owner_name='Alex Owner',
            guest_owner_phone='09123456789',
            guest_owner_email='alex.one@example.com',
            guest_owner_address='First address',
        )
        second_pet = Pet.objects.create(
            name='Luna',
            source=Pet.Source.WALKIN,
            guest_owner_name='Alex Owner',
            guest_owner_phone='09987654321',
            guest_owner_email='alex.two@example.com',
            guest_owner_address='Second address',
        )

        response = self.client.get(reverse('records:admin_create'))

        self.assertEqual(response.status_code, 200)
        guest_pets = [
            pet for pet in json.loads(response.context['pets_list_json'])
            if pet['source'] == Pet.Source.WALKIN
        ]
        self.assertEqual(
            {(pet['id'], pet['owner_contact'], pet['owner_email']) for pet in guest_pets},
            {
                (first_pet.pk, '09123456789', 'alex.one@example.com'),
                (second_pet.pk, '09987654321', 'alex.two@example.com'),
            },
        )
        self.assertContains(response, 'guest.phone, guest.email')

    def test_create_rejects_selected_guest_pet_from_different_contact_identity(self):
        pet = Pet.objects.create(
            name='Milo',
            source=Pet.Source.WALKIN,
            guest_owner_name='Alex Owner',
            guest_owner_phone='09123456789',
            guest_owner_email='alex.one@example.com',
            guest_owner_address='First address',
        )

        response = self.client.post(reverse('records:admin_create'), {
            'vet': self.vet.pk,
            'date_recorded': '2026-10-17',
            'history_clinical_signs': 'Routine examination',
            'treatment': 'Examination completed',
            'rx': 'None',
            'action_required': ClinicalStatus.get_default().pk,
            'client_source': 'WALKIN',
            'selected_guest_owner': '1',
            'owner_name': 'Alex Owner',
            'owner_contact': '09987654321',
            'owner_email': 'alex.two@example.com',
            'owner_address': 'Second address',
            'selected_pet_id': pet.pk,
            'pet_name': pet.name,
            'pet_species': 'Dog',
            'pet_sex': 'MALE',
            'pet_color': 'Brown',
            'branch': self.branch.pk,
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'The selected pet does not match this owner.')
        self.assertFalse(MedicalRecord.objects.filter(pet=pet).exists())

    def test_owner_identity_check_marks_same_guest_when_name_phone_and_email_match(self):
        Pet.objects.create(
            name='Milo',
            source=Pet.Source.WALKIN,
            guest_owner_name='Alex Owner',
            guest_owner_phone='09123456789',
            guest_owner_email='alex.owner@example.com',
        )

        response = self.client.get(reverse('records:api_check_owner_identity'), {
            'name': 'Alex Owner',
            'phone': '09123456789',
            'email': 'alex.owner@example.com',
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['same_guest'])

    def test_owner_identity_check_warns_for_same_name_with_different_phone_and_email(self):
        Pet.objects.create(
            name='Milo',
            source=Pet.Source.WALKIN,
            guest_owner_name='Alex Owner',
            guest_owner_phone='09123456789',
            guest_owner_email='alex.owner@example.com',
        )

        response = self.client.get(reverse('records:api_check_owner_identity'), {
            'name': 'Alex Owner',
            'phone': '09987654321',
            'email': 'different.owner@example.com',
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['name_match'])
        self.assertFalse(response.json()['identity_match'])
        self.assertFalse(response.json()['same_guest'])

    def test_medical_record_edit_prefills_clinical_tracking_from_first_entry(self):
        first_status = ClinicalStatus.get_default()
        later_status = ClinicalStatus.objects.create(
            name='Later follow-up action',
            code='LATER_FOLLOW_UP_ACTION',
        )
        pet = Pet.objects.create(
            source=Pet.Source.WALKIN,
            guest_owner_name='Clinical Tracking Owner',
            guest_owner_phone='09123456789',
            guest_owner_email='clinical-tracking-owner@example.com',
            name='Clinical Tracking Patient',
            species='Dog',
            sex=Pet.Sex.MALE,
            color='Brown',
        )
        record = MedicalRecord.objects.create(
            pet=pet,
            branch=self.branch,
            vet=self.vet,
            date_recorded='2026-10-18',
            weight=20,
            temperature=39,
            history_clinical_signs='Latest visit signs',
            treatment='Latest visit treatment',
            rx='Latest visit prescription',
        )
        first_entry = RecordEntry.objects.create(
            record=record,
            vet=self.vet,
            date_recorded='2026-10-17',
            weight=15,
            temperature=38,
            history_clinical_signs='First visit signs',
            treatment='First visit treatment',
            rx='First visit prescription',
            action_required=first_status,
        )
        RecordEntry.objects.create(
            record=record,
            vet=self.vet,
            date_recorded='2026-10-18',
            weight=20,
            temperature=39,
            history_clinical_signs='Latest visit signs',
            treatment='Latest visit treatment',
            rx='Latest visit prescription',
            action_required=later_status,
        )

        response = self.client.get(reverse('records:admin_edit', args=[record.pk]))

        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertEqual(
            form['date_recorded'].value().isoformat(),
            str(first_entry.date_recorded),
        )
        self.assertEqual(form['weight'].value(), first_entry.weight)
        self.assertEqual(form['temperature'].value(), first_entry.temperature)
        self.assertEqual(
            form['history_clinical_signs'].value(),
            first_entry.history_clinical_signs,
        )
        self.assertEqual(form['treatment'].value(), first_entry.treatment)
        self.assertEqual(form['rx'].value(), first_entry.rx)
        self.assertEqual(form['action_required'].value(), first_status.pk)
        self.assertContains(
            response,
            "Save these changes to",
        )
        self.assertContains(
            response,
            "medical record? The record and its first visit information will be updated.",
        )
        self.assertContains(response, 'bindCenteredFormConfirmation')

        entry_edit_response = self.client.get(
            reverse('records:admin_entry_edit', args=[first_entry.pk]),
        )
        self.assertEqual(entry_edit_response.status_code, 200)
        self.assertContains(
            entry_edit_response,
            "updated clinical notes and visit details will be saved.",
        )
        self.assertContains(entry_edit_response, 'bindCenteredFormConfirmation')

        detail_response = self.client.get(
            reverse('records:admin_detail', args=[record.pk]),
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(
            detail_response,
            "updated clinical notes and visit details will be saved.",
        )
        self.assertContains(detail_response, 'bindCenteredFormConfirmation')

    @patch('records.views.pisa.pisaDocument')
    def test_pdf_download_allows_missing_weight_and_temperature(self, render_pdf):
        pet = Pet.objects.create(
            source=Pet.Source.WALKIN,
            guest_owner_name='PDF Test Owner',
            guest_owner_phone='09123456789',
            guest_owner_address='1 Clinic Road',
            name='PDF Test Patient',
            species='Dog',
            breed='Mixed',
            sex=Pet.Sex.MALE,
            color='Brown',
            date_of_birth='2020-01-01',
        )
        record = MedicalRecord.objects.create(
            pet=pet,
            branch=self.branch,
            vet=self.vet,
            date_recorded='2026-10-18',
        )
        entries = [
            RecordEntry.objects.create(
                record=record,
                vet=self.vet,
                date_recorded='2026-10-18',
                history_clinical_signs='Routine examination',
                treatment='Examination completed',
                rx='None',
            ),
        ]
        def fake_pdf_renderer(_source, destination, **_kwargs):
            destination.write(b'%PDF-test')
            return SimpleNamespace(err=0)

        render_pdf.side_effect = fake_pdf_renderer

        detail_response = self.client.get(
            reverse('records:admin_detail', args=[record.pk]),
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(
            detail_response.context['pdf_blocking_fields'],
            [],
        )
        self.assertContains(detail_response, 'PDF is available')

        pdf_response = self.client.get(
            reverse('records:download_pdf', args=[record.pk]),
        )

        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response['Content-Type'], 'application/pdf')
        self.assertEqual(pdf_response.content, b'%PDF-test')
        self.assertEqual(get_record_pdf_blocking_fields(record, entries), [])

    def test_missing_clinical_notes_still_block_pdf_download(self):
        pet = Pet.objects.create(
            source=Pet.Source.WALKIN,
            guest_owner_name='PDF Test Owner',
            guest_owner_phone='09123456789',
            guest_owner_address='1 Clinic Road',
            name='PDF Test Patient',
            species='Dog',
            breed='Mixed',
            sex=Pet.Sex.MALE,
            color='Brown',
            date_of_birth='2020-01-01',
        )
        record = MedicalRecord.objects.create(
            pet=pet,
            branch=self.branch,
            vet=self.vet,
            date_recorded='2026-10-18',
        )
        entry = RecordEntry.objects.create(
            record=record,
            vet=self.vet,
            date_recorded='2026-10-18',
            treatment='Examination completed',
            rx='None',
        )

        blocking_fields = get_record_pdf_blocking_fields(
            record,
            [entry],
        )

        self.assertIn(
            'Visit entry #1: History/Clinical Signs is missing.',
            blocking_fields,
        )
        self.assertNotIn('Visit entry #1: Weight is missing.', blocking_fields)
        self.assertNotIn('Visit entry #1: Temperature is missing.', blocking_fields)

    def test_medical_record_edit_updates_first_entry_not_later_entries(self):
        first_status = ClinicalStatus.get_default()
        later_status = ClinicalStatus.objects.create(
            name='Later follow-up action',
            code='LATER_FOLLOW_UP_ACTION',
        )
        pet = Pet.objects.create(
            source=Pet.Source.WALKIN,
            guest_owner_name='Clinical Tracking Owner',
            guest_owner_phone='09123456789',
            guest_owner_email='clinical-tracking-owner@example.com',
            name='Clinical Tracking Patient',
            species='Dog',
            sex=Pet.Sex.MALE,
            color='Brown',
        )
        record = MedicalRecord.objects.create(
            pet=pet,
            branch=self.branch,
            vet=self.vet,
            date_recorded='2026-10-18',
        )
        first_entry = RecordEntry.objects.create(
            record=record,
            vet=self.vet,
            date_recorded='2026-10-17',
            history_clinical_signs='First visit signs',
            treatment='First visit treatment',
            rx='First visit prescription',
            action_required=first_status,
        )
        later_entry = RecordEntry.objects.create(
            record=record,
            vet=self.vet,
            date_recorded='2026-10-18',
            history_clinical_signs='Later visit signs',
            treatment='Later visit treatment',
            rx='Later visit prescription',
            action_required=later_status,
        )

        response = self.client.post(
            reverse('records:admin_edit', args=[record.pk]),
            {
                'owner_name': pet.guest_owner_name,
                'owner_contact': pet.guest_owner_phone,
                'owner_address': '',
                'owner_email': pet.guest_owner_email,
                'pet_name': pet.name,
                'pet_species': pet.species,
                'pet_sex': pet.sex,
                'pet_color': pet.color,
                'branch': self.branch.pk,
                'vet': self.vet.pk,
                'date_recorded': '2026-10-19',
                'weight': '16.5',
                'temperature': '38.5',
                'history_clinical_signs': 'Corrected first visit signs',
                'treatment': 'Corrected first visit treatment',
                'rx': 'Corrected first visit prescription',
                'action_required': first_status.pk,
            },
        )

        self.assertEqual(response.status_code, 302)
        first_entry.refresh_from_db()
        later_entry.refresh_from_db()
        self.assertEqual(first_entry.date_recorded.isoformat(), '2026-10-19')
        self.assertEqual(first_entry.history_clinical_signs, 'Corrected first visit signs')
        self.assertEqual(first_entry.action_required_id, first_status.pk)
        self.assertEqual(later_entry.date_recorded.isoformat(), '2026-10-18')
        self.assertEqual(later_entry.history_clinical_signs, 'Later visit signs')
        self.assertEqual(later_entry.action_required_id, later_status.pk)

    def test_create_rejects_duplicate_portal_pet_without_updating_owner_or_pet(self):
        owner = get_user_model().objects.create_user(
            username='duplicate-record-owner',
            email='duplicate-record-owner@example.com',
            password='A-secure-test-password-923!',
            phone_number='09123456789',
            address='Original owner address',
        )
        pet = Pet.objects.create(
            name='Milo',
            owner=owner,
            species='Cat',
            sex=Pet.Sex.MALE,
            color='Black',
        )

        response = self.client.post(reverse('records:admin_create'), {
            'vet': self.vet.pk,
            'date_recorded': '2026-10-17',
            'history_clinical_signs': 'Routine examination',
            'treatment': 'Examination completed',
            'rx': 'None',
            'action_required': ClinicalStatus.get_default().pk,
            'client_source': 'PORTAL',
            'selected_user_id': owner.pk,
            'owner_name': 'Duplicate Record Owner',
            'owner_contact': '09987654321',
            'owner_address': 'Changed owner address',
            'pet_name': ' milo ',
            'pet_species': 'Dog',
            'pet_sex': 'FEMALE',
            'pet_color': 'White',
            'branch': self.branch.pk,
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'already registered to this account')
        owner.refresh_from_db()
        pet.refresh_from_db()
        self.assertEqual(owner.phone_number, '09123456789')
        self.assertEqual(owner.address, 'Original owner address')
        self.assertEqual((pet.species, pet.sex, pet.color), ('Cat', Pet.Sex.MALE, 'Black'))
        self.assertFalse(MedicalRecord.objects.filter(pet=pet).exists())

    def test_create_rejects_duplicate_guest_pet(self):
        Pet.objects.create(
            name='Luna',
            source=Pet.Source.WALKIN,
            guest_owner_name='Guest Record Owner',
            guest_owner_phone='09123456789',
            species='Cat',
            sex=Pet.Sex.FEMALE,
            color='Gray',
        )

        response = self.client.post(reverse('records:admin_create'), {
            'vet': self.vet.pk,
            'date_recorded': '2026-10-17',
            'history_clinical_signs': 'Routine examination',
            'treatment': 'Examination completed',
            'rx': 'None',
            'action_required': ClinicalStatus.get_default().pk,
            'client_source': 'WALKIN',
            'selected_guest_owner': '1',
            'owner_name': 'Guest Record Owner',
            'owner_contact': '09123456789',
            'owner_address': 'Guest address',
            'pet_name': 'luna',
            'pet_species': 'Dog',
            'pet_sex': 'MALE',
            'pet_color': 'Brown',
            'branch': self.branch.pk,
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'already registered for this guest owner')
        self.assertEqual(Pet.objects.filter(guest_owner_name='Guest Record Owner').count(), 1)
        self.assertEqual(MedicalRecord.objects.count(), 0)

    def test_create_syncs_portal_email_and_requires_reverification(self):
        owner, pet, appointment, entry_data = self._appointment_record_setup()
        owner.email_verified = True
        owner.save(update_fields=['email_verified'])
        entry_data.update({
            'client_source': 'PORTAL',
            'selected_user_id': owner.pk,
            'selected_pet_id': pet.pk,
            'owner_name': 'Appointment Record Owner',
            'owner_contact': owner.phone_number,
            'owner_address': '',
            'owner_email': 'updated-owner@example.com',
            'pet_name': pet.name,
            'pet_species': pet.species,
            'pet_sex': 'FEMALE',
            'pet_color': pet.color,
            'branch': self.branch.pk,
        })

        response = self.client.post(reverse('records:admin_create'), entry_data)

        self.assertEqual(response.status_code, 302)
        owner.refresh_from_db()
        pet.refresh_from_db()
        appointment.refresh_from_db()
        self.assertEqual(owner.email, 'updated-owner@example.com')
        self.assertFalse(owner.email_verified)
        self.assertEqual(pet.owner_display_email, 'updated-owner@example.com')
        self.assertEqual(appointment.current_owner_email, 'updated-owner@example.com')

    def test_edit_keeps_portal_owner_contact_details_read_only(self):
        owner = get_user_model().objects.create_user(
            username='medical-record-edit-owner',
            email='original-owner@example.com',
            password='A-secure-test-password-923!',
            phone_number='09123456789',
            email_verified=True,
        )
        pet = Pet.objects.create(
            name='Medical Record Edit Pet',
            owner=owner,
            species='Cat',
            sex=Pet.Sex.FEMALE,
            color='Black',
        )
        record = MedicalRecord.objects.create(
            pet=pet,
            branch=self.branch,
            vet=self.vet,
            date_recorded='2026-10-17',
        )
        RecordEntry.objects.create(
            record=record,
            vet=self.vet,
            date_recorded='2026-10-17',
            history_clinical_signs='Routine examination',
            treatment='Examination completed',
            rx='None',
            action_required=ClinicalStatus.get_default(),
        )

        edit_url = reverse('records:admin_edit', args=[record.pk])
        edit_response = self.client.get(edit_url)
        self.assertEqual(edit_response.status_code, 200)
        self.assertContains(edit_response, 'value="Portal (Registered User)"')
        self.assertContains(edit_response, 'Owner Name *')
        self.assertContains(edit_response, 'Email Address *')
        self.assertRegex(
            edit_response.content.decode(),
            r'id="ro-owner-email"[^>]*required',
        )
        self.assertEqual(
            edit_response.context['form']['owner_email'].value(),
            'original-owner@example.com',
        )
        self.assertRegex(
            edit_response.content.decode(),
            r'name="owner_name"[^>]*readonly',
        )
        self.assertRegex(
            edit_response.content.decode(),
            r'id="ro-owner-email"[^>]*readonly',
        )
        self.assertNotContains(edit_response, 'name="client_source"')
        self.assertNotContains(edit_response, 'guest-owner-name-conflict-note')
        self.assertContains(edit_response, 'Consultation Information')
        self.assertTrue(edit_response.context['form'].fields['owner_email'].required)

        response = self.client.post(
            edit_url,
            {
                'owner_name': 'Changed Owner Name',
                'owner_contact': '09999999999',
                'owner_address': 'Changed address',
                'owner_email': 'edited-owner@example.com',
                'pet_name': pet.name,
                'pet_species': pet.species,
                'pet_sex': 'FEMALE',
                'pet_color': pet.color,
                'branch': self.branch.pk,
                'vet': self.vet.pk,
                'date_recorded': '2026-10-17',
                'history_clinical_signs': 'Routine examination',
                'treatment': 'Examination completed',
                'rx': 'None',
                'action_required': ClinicalStatus.get_default().pk,
            },
        )

        self.assertEqual(response.status_code, 302)
        owner.refresh_from_db()
        pet.refresh_from_db()
        self.assertEqual(owner.email, 'original-owner@example.com')
        self.assertTrue(owner.email_verified)
        self.assertEqual(owner.phone_number, '09123456789')
        self.assertEqual(owner.address, '')
        self.assertEqual(pet.owner_id, owner.pk)
        self.assertEqual(pet.owner_display_email, 'original-owner@example.com')

    def test_edit_keeps_guest_owner_details_editable_and_saves_updates(self):
        pet = Pet.objects.create(
            source=Pet.Source.WALKIN,
            guest_owner_name='Original Guest',
            guest_owner_phone='09123456789',
            guest_owner_email='original-guest@example.com',
            guest_owner_address='Original address',
            name='Guest Medical Record Edit Pet',
            species='Cat',
            sex=Pet.Sex.FEMALE,
            color='Black',
        )
        record = MedicalRecord.objects.create(
            pet=pet,
            branch=self.branch,
            vet=self.vet,
            date_recorded='2026-10-17',
        )
        Pet.objects.create(
            source=Pet.Source.WALKIN,
            guest_owner_name='Updated Guest',
            guest_owner_email='updated-guest@example.com',
            name='Another Guest Pet',
            species='Dog',
            sex=Pet.Sex.MALE,
        )
        RecordEntry.objects.create(
            record=record,
            vet=self.vet,
            date_recorded='2026-10-17',
            history_clinical_signs='Routine examination',
            treatment='Examination completed',
            rx='None',
            action_required=ClinicalStatus.get_default(),
        )

        edit_url = reverse('records:admin_edit', args=[record.pk])
        edit_response = self.client.get(edit_url)
        self.assertEqual(edit_response.status_code, 200)
        self.assertContains(edit_response, 'value="Walk-in (Guest)"')
        self.assertContains(edit_response, 'Email Address *')
        self.assertContains(edit_response, 'guest-owner-name-conflict-note')
        self.assertContains(edit_response, 'guest-owner-email-conflict-note')
        self.assertContains(edit_response, 'api/check-guest-owner-edit-conflicts/')
        self.assertTrue(edit_response.context['form'].fields['owner_email'].required)
        self.assertNotRegex(
            edit_response.content.decode(),
            r'name="owner_name"[^>]*readonly',
        )
        self.assertNotContains(edit_response, 'name="client_source"')

        response = self.client.post(
            edit_url,
            {
                'owner_name': 'Updated Guest',
                'owner_contact': '09987654321',
                'owner_address': 'Updated address',
                'owner_email': 'updated-guest@example.com',
                'pet_name': pet.name,
                'pet_species': pet.species,
                'pet_sex': 'FEMALE',
                'pet_color': pet.color,
                'branch': self.branch.pk,
                'vet': self.vet.pk,
                'date_recorded': '2026-10-17',
                'history_clinical_signs': 'Routine examination',
                'treatment': 'Examination completed',
                'rx': 'None',
                'action_required': ClinicalStatus.get_default().pk,
            },
        )

        self.assertEqual(response.status_code, 302)
        pet.refresh_from_db()
        self.assertEqual(pet.guest_owner_name, 'Updated Guest')
        self.assertEqual(pet.guest_owner_phone, '09987654321')
        self.assertEqual(pet.guest_owner_email, 'updated-guest@example.com')
        self.assertEqual(pet.guest_owner_address, 'Updated address')

    def test_edit_blocks_changing_guest_email_to_registered_portal_email(self):
        portal_owner = get_user_model().objects.create_user(
            username='registered-email-conflict',
            first_name='Registered',
            last_name='Owner',
            email='registered-email-conflict@example.com',
            password='A-secure-test-password-923!',
        )
        pet = Pet.objects.create(
            source=Pet.Source.WALKIN,
            guest_owner_name='Original Guest',
            guest_owner_phone='09123456789',
            guest_owner_email='original-guest@example.com',
            name='Guest Email Conflict Pet',
            species='Cat',
            sex=Pet.Sex.FEMALE,
            color='Black',
        )
        record = MedicalRecord.objects.create(
            pet=pet,
            branch=self.branch,
            vet=self.vet,
            date_recorded='2026-10-17',
        )
        RecordEntry.objects.create(
            record=record,
            vet=self.vet,
            date_recorded='2026-10-17',
            history_clinical_signs='Routine examination',
            treatment='Examination completed',
            rx='None',
            action_required=ClinicalStatus.get_default(),
        )

        response = self.client.post(
            reverse('records:admin_edit', args=[record.pk]),
            {
                'owner_name': 'Registered Owner',
                'owner_contact': '09987654321',
                'owner_address': 'Updated address',
                'owner_email': portal_owner.email,
                'pet_name': pet.name,
                'pet_species': pet.species,
                'pet_sex': 'FEMALE',
                'pet_color': pet.color,
                'branch': self.branch.pk,
                'vet': self.vet.pk,
                'date_recorded': '2026-10-17',
                'history_clinical_signs': 'Routine examination',
                'treatment': 'Examination completed',
                'rx': 'None',
                'action_required': ClinicalStatus.get_default().pk,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('owner_email', response.context['form'].errors)
        self.assertIn('registered portal account', response.context['form'].errors['owner_email'][0])
        pet.refresh_from_db()
        self.assertEqual(pet.guest_owner_name, 'Original Guest')
        self.assertEqual(pet.guest_owner_email, 'original-guest@example.com')

    def test_guest_owner_edit_conflict_api_distinguishes_registered_and_guest_matches(self):
        registered_owner = get_user_model().objects.create_user(
            username='edit-conflict-registered-owner',
            first_name='Morgan',
            last_name='Portal',
            email='morgan-portal@example.com',
            password='A-secure-test-password-923!',
        )
        matching_guest = Pet.objects.create(
            source=Pet.Source.WALKIN,
            guest_owner_name='Jamie Guest',
            guest_owner_email='jamie-guest@example.com',
            name='Matching Guest Pet',
            species='Dog',
            sex=Pet.Sex.MALE,
        )
        current_pet = Pet.objects.create(
            source=Pet.Source.WALKIN,
            guest_owner_name='Current Guest',
            guest_owner_email='current-guest@example.com',
            name='Current Edit Pet',
            species='Cat',
            sex=Pet.Sex.FEMALE,
        )
        Appointment.objects.create(
            source=Appointment.Source.WALKIN,
            owner_name='Taylor Appointment Guest',
            owner_email='taylor-appointment-guest@example.com',
            owner_phone='09123456789',
            pet_name='Appointment Guest Pet',
            branch=self.branch,
            appointment_date=date(2026, 10, 27),
            appointment_time=time(10),
            status=Appointment.Status.COMPLETED,
        )
        endpoint = reverse('records:api_check_guest_owner_edit_conflicts')

        registered_response = self.client.get(endpoint, {
            'name': 'Morgan Portal',
            'email': registered_owner.email,
            'pet_id': current_pet.pk,
        })
        self.assertEqual(registered_response.status_code, 200)
        self.assertEqual(registered_response.json(), {
            'registered_name_match': True,
            'guest_name_match': False,
            'registered_email_match': True,
            'guest_email_match': False,
        })

        guest_response = self.client.get(endpoint, {
            'name': 'Jamie Guest',
            'email': 'jamie-guest@example.com',
            'pet_id': current_pet.pk,
        })
        self.assertEqual(guest_response.status_code, 200)
        self.assertEqual(guest_response.json(), {
            'registered_name_match': False,
            'guest_name_match': True,
            'registered_email_match': False,
            'guest_email_match': True,
        })

        appointment_guest_response = self.client.get(endpoint, {
            'name': 'Taylor Appointment Guest',
            'email': 'taylor-appointment-guest@example.com',
            'pet_id': current_pet.pk,
        })
        self.assertEqual(appointment_guest_response.status_code, 200)
        self.assertEqual(appointment_guest_response.json(), {
            'registered_name_match': False,
            'guest_name_match': True,
            'registered_email_match': False,
            'guest_email_match': True,
        })

        own_email_response = self.client.get(endpoint, {
            'name': current_pet.guest_owner_name,
            'email': current_pet.guest_owner_email,
            'pet_id': current_pet.pk,
        })
        self.assertEqual(own_email_response.status_code, 200)
        self.assertFalse(own_email_response.json()['guest_email_match'])

        self.assertTrue(Pet.objects.filter(pk=matching_guest.pk).exists())

    def test_create_rejects_new_guest_when_owner_name_and_phone_match_portal_owner(self):
        get_user_model().objects.create_user(
            username='existing-owner-identity',
            first_name='Taylor',
            last_name='Owner',
            email='taylor-owner@example.com',
            phone_number='09123456789',
        )

        response = self.client.post(reverse('records:admin_create'), {
            'vet': self.vet.pk,
            'date_recorded': '2026-10-17',
            'history_clinical_signs': 'Routine examination',
            'treatment': 'Examination completed',
            'rx': 'None',
            'action_required': ClinicalStatus.get_default().pk,
            'client_source': 'WALKIN',
            'owner_name': 'Taylor Owner',
            'owner_contact': '09123456789',
            'owner_address': 'Guest address',
            'pet_name': 'Poppy',
            'pet_species': 'Dog',
            'pet_sex': 'FEMALE',
            'pet_color': 'Brown',
            'branch': self.branch.pk,
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'contact number is already registered')
        self.assertFalse(Pet.objects.filter(name='Poppy').exists())
        self.assertEqual(MedicalRecord.objects.count(), 0)

    def test_new_guest_with_same_name_but_different_phone_can_be_registered(self):
        get_user_model().objects.create_user(
            username='same-name-different-client',
            first_name='Taylor',
            last_name='Owner',
            email='taylor-owner@example.com',
            phone_number='09123456789',
        )

        response = self.client.post(reverse('records:admin_create'), {
            'vet': self.vet.pk,
            'date_recorded': '2026-10-17',
            'history_clinical_signs': 'Routine examination',
            'treatment': 'Examination completed',
            'rx': 'None',
            'action_required': ClinicalStatus.get_default().pk,
            'client_source': 'WALKIN',
            'owner_name': 'Taylor Owner',
            'owner_contact': '09987654321',
            'owner_address': 'Different guest address',
            'owner_email': 'guest-owner@example.com',
            'pet_name': 'Poppy',
            'pet_species': 'Dog',
            'pet_sex': 'FEMALE',
            'pet_color': 'Brown',
            'branch': self.branch.pk,
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Pet.objects.filter(
            name='Poppy',
            guest_owner_phone='09987654321',
            guest_owner_email='guest-owner@example.com',
        ).exists())

    def test_add_visit_entry_defaults_to_logged_in_vet_and_clinic_over_record(self):
        previous_vet_user = get_user_model().objects.create_user(
            username='previous-record-vet',
            assigned_role=self.user.assigned_role,
        )
        previous_vet = StaffMember.objects.create(
            user=previous_vet_user,
            first_name='Previous',
            last_name='Veterinarian',
            position=StaffMember.Position.VETERINARIAN,
            branch=self.branch,
        )
        record_branch = Branch.objects.create(name='Pet Owner Branch')
        pet = Pet.objects.create(
            name='Attending Vet Pet',
            species='Dog',
            sex=Pet.Sex.FEMALE,
        )
        record = MedicalRecord.objects.create(
            pet=pet,
            vet=previous_vet,
            branch=record_branch,
            date_recorded='2026-10-17',
        )

        response = self.client.get(
            reverse('records:admin_add_entry', args=[record.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form']['vet'].value(), self.vet.pk)
        self.assertEqual(response.context['service_branch_id'], self.branch.pk)
        self.assertEqual(response.context['selected_branch_id'], str(self.branch.pk))
        page_html = response.content.decode()
        self.assertLess(
            page_html.index('Temperature (°C)'),
            page_html.index('Weight (kg)'),
        )
        self.assertLess(
            page_html.index('Attending Veterinarian *'),
            page_html.index('Branch / Location *'),
        )
        reason_label = page_html.index('Follow-Up Reason')
        self.assertIn(
            'form-group form-group--full',
            page_html[reason_label - 100:reason_label],
        )

    def test_linked_appointment_branch_and_vet_override_current_veterinarian(self):
        appointment_branch = Branch.objects.create(name='Appointment Clinic Branch')
        assigned_user = get_user_model().objects.create_user(
            username='appointment-assigned-vet',
            assigned_role=self.user.assigned_role,
            branch=appointment_branch,
        )
        assigned_vet = StaffMember.objects.create(
            user=assigned_user,
            first_name='Appointment',
            last_name='Veterinarian',
            position=StaffMember.Position.VETERINARIAN,
            branch=appointment_branch,
        )
        pet = Pet.objects.create(
            name='Appointment Linked Pet',
            species='Cat',
            sex=Pet.Sex.FEMALE,
        )
        record = MedicalRecord.objects.create(
            pet=pet,
            branch=self.branch,
            vet=self.vet,
            date_recorded='2026-10-17',
        )
        appointment = Appointment.objects.create(
            owner_name='Appointment Pet Owner',
            pet_name=pet.name,
            pet=pet,
            branch=appointment_branch,
            preferred_vet=assigned_vet,
            appointment_date=date(2026, 10, 17),
            appointment_time=time(11),
            status=Appointment.Status.COMPLETED,
        )

        response = self.client.get(
            reverse('records:admin_add_entry', args=[record.pk]),
            {'appointment': appointment.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['service_branch_id'], appointment_branch.pk)
        self.assertEqual(response.context['form']['vet'].value(), assigned_vet.pk)

    def _appointment_record_setup(self):
        owner = get_user_model().objects.create_user(
            username='appointment-record-owner',
            email='appointment-record-owner@example.com',
            password='A-secure-test-password-923!',
            phone_number='09123456789',
        )
        pet = Pet.objects.create(
            name='Appointment Record Pet',
            owner=owner,
            species='Cat',
            sex=Pet.Sex.FEMALE,
            color='Black',
        )
        appointment = Appointment.objects.create(
            owner_name='Appointment Record Owner',
            owner_email=owner.email,
            owner_phone=owner.phone_number,
            pet_name=pet.name,
            pet=pet,
            user=owner,
            branch=self.branch,
            appointment_date=date(2026, 10, 17),
            appointment_time=time(11),
            status=Appointment.Status.COMPLETED,
        )
        entry_data = {
            'appointment': appointment.pk,
            'vet': self.vet.pk,
            'date_recorded': '2026-10-17',
            'history_clinical_signs': 'Routine examination',
            'treatment': 'Examination completed',
            'rx': 'None',
            'action_required': ClinicalStatus.get_default().pk,
        }
        return owner, pet, appointment, entry_data

    def test_creating_appointment_medical_record_returns_to_appointment(self):
        owner, pet, appointment, entry_data = self._appointment_record_setup()
        entry_data.update({
            'client_source': 'PORTAL',
            'selected_user_id': owner.pk,
            'owner_name': 'Appointment Record Owner',
            'owner_contact': owner.phone_number,
            'owner_address': '',
            'pet_name': pet.name,
            'selected_pet_id': pet.pk,
            'pet_species': pet.species,
            'pet_sex': 'FEMALE',
            'pet_color': pet.color,
            'branch': self.branch.pk,
        })

        response = self.client.post(
            reverse('records:admin_create'),
            entry_data,
        )

        self.assertRedirects(
            response,
            reverse('appointments:admin_detail', args=[appointment.pk]),
            fetch_redirect_response=False,
        )
        self.assertTrue(MedicalRecord.objects.filter(pet=pet).exists())
        self.assertEqual(
            [str(message) for message in get_messages(response.wsgi_request)],
            ['Medical record saved. Continue with this appointment.'],
        )

    def test_adding_entry_from_appointment_returns_to_appointment(self):
        _, pet, appointment, entry_data = self._appointment_record_setup()
        record = MedicalRecord.objects.create(
            pet=pet,
            branch=self.branch,
            vet=self.vet,
            date_recorded=date(2026, 10, 17),
        )
        entry_data['branch_id'] = self.branch.pk

        response = self.client.post(
            reverse('records:admin_add_entry', args=[record.pk]),
            entry_data,
        )

        self.assertRedirects(
            response,
            reverse('appointments:admin_detail', args=[appointment.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            [str(message) for message in get_messages(response.wsgi_request)],
            ['Medical record saved. Continue with this appointment.'],
        )


class MedicalFileValidationTests(SimpleTestCase):
    def test_pdf_requires_pdf_signature(self):
        upload = SimpleUploadedFile('result.pdf', b'not a pdf')

        with self.assertRaises(ValidationError):
            validate_medical_file(upload)

    def test_oversized_file_is_rejected(self):
        upload = SimpleUploadedFile('result.pdf', b'%PDF-' + b'x' * (20 * 1024 * 1024))

        with self.assertRaises(ValidationError):
            validate_medical_file(upload)

    def test_valid_pdf_is_accepted(self):
        upload = SimpleUploadedFile('result.pdf', b'%PDF-1.7 test document')

        validate_medical_file(upload)


class LaboratoryTypeSettingsTests(SimpleTestCase):
    @patch('settings.forms.get_setting')
    def test_laboratory_types_can_be_added_and_duplicates_are_removed(self, get_setting):
        get_setting.side_effect = lambda key, default=None: (
            ['Laboratory Result'] if key == 'medical_laboratory_type_options' else default
        )
        form = MedicalRecordsSettingsForm(data={
            'laboratory_types': 'CBC\nBlood Chemistry\nCBC',
        })

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['laboratory_types'], ['CBC', 'Blood Chemistry'])

    @patch('settings.forms.get_setting')
    def test_laboratory_type_list_cannot_be_empty(self, get_setting):
        get_setting.side_effect = lambda key, default=None: (
            ['Laboratory Result'] if key == 'medical_laboratory_type_options' else default
        )
        form = MedicalRecordsSettingsForm(data={
            'laboratory_types': '  \n',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('laboratory_types', form.errors)

    def test_removed_medical_controls_are_not_available(self):
        form = MedicalRecordsSettingsForm()

        self.assertNotIn('default_followup_days', form.fields)
        self.assertNotIn('vaccination_reminders', form.fields)
        self.assertNotIn('reminder_days_before', form.fields)
        self.assertNotIn('clinical_status_auto_actions', form.fields)

    def test_laboratory_images_accept_png_and_jpeg(self):
        for filename in ('result.png', 'result.jpg', 'result.jpeg'):
            with self.subTest(filename=filename):
                upload = SimpleUploadedFile(filename, b'image data')
                validate_laboratory_image(upload)

    def test_laboratory_images_reject_non_image_files(self):
        upload = SimpleUploadedFile('result.pdf', b'%PDF-1.7 test document')

        with self.assertRaises(ValidationError):
            validate_laboratory_image(upload)

    def test_laboratory_images_are_limited_to_10_mb(self):
        upload = SimpleUploadedFile('result.png', b'x' * (10 * 1024 * 1024 + 1))

        with self.assertRaises(ValidationError):
            validate_laboratory_image(upload)


class PdfAssetResolutionTests(SimpleTestCase):
    def test_pdf_stylesheet_is_available_for_inline_rendering(self):
        stylesheet = _get_pdf_styles()

        self.assertIn('.section-header', stylesheet)
        self.assertIn('background-color: #333', stylesheet)
        self.assertIn('.owner-info-table .section-header', stylesheet)
        self.assertIn('.owner-info-table {\n    table-layout: fixed;\n    width: 100%;', stylesheet)

    def test_media_assets_are_resolved_to_local_files(self):
        with tempfile.TemporaryDirectory() as media_root:
            logo_path = os.path.join(media_root, 'branches', 'logo.png')
            os.makedirs(os.path.dirname(logo_path))
            with open(logo_path, 'wb') as logo_file:
                logo_file.write(b'logo')

            with override_settings(MEDIA_ROOT=media_root, MEDIA_URL='/media/'):
                resolved_path = _pdf_link_callback('/media/branches/logo.png', '')

            self.assertEqual(resolved_path, logo_path)
