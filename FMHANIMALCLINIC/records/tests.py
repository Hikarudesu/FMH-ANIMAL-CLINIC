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
from .views import _get_pdf_styles, _pdf_link_callback
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
        self.assertContains(response, 'An owner with this name may already exist.')
        self.assertContains(response, 'name="selected_guest_owner"')
        self.assertContains(response, "result.addEventListener('mousedown'")
        self.assertContains(response, 'name="owner_email"')

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
        self.assertRegex(
            edit_response.content.decode(),
            r'name="owner_name"[^>]*readonly',
        )
        self.assertNotContains(edit_response, 'name="client_source"')
        self.assertContains(edit_response, 'Consultation Information')

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

    def test_media_assets_are_resolved_to_local_files(self):
        with tempfile.TemporaryDirectory() as media_root:
            logo_path = os.path.join(media_root, 'branches', 'logo.png')
            os.makedirs(os.path.dirname(logo_path))
            with open(logo_path, 'wb') as logo_file:
                logo_file.write(b'logo')

            with override_settings(MEDIA_ROOT=media_root, MEDIA_URL='/media/'):
                resolved_path = _pdf_link_callback('/media/branches/logo.png', '')

            self.assertEqual(resolved_path, logo_path)
