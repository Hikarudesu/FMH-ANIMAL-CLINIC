from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.rbac_models import Module, ModulePermission, Role
from branches.models import Branch
from patients.models import Pet
from records.models import MedicalRecord
from .forms import AdminPetForm, PetForm


class AdminPetWalkInContactTests(TestCase):
    def setUp(self):
        self.form_data = {
            'source': 'WALKIN',
            'guest_owner_name': 'Walk-in Owner',
            'guest_owner_phone': '09123456789',
            'guest_owner_email': 'owner@example.com',
            'name': 'Buddy',
            'species': 'Dog',
            'sex': 'MALE',
            'is_active': 'on',
        }

    def test_walkin_patient_requires_phone_number(self):
        form_data = self.form_data.copy()
        form_data['guest_owner_phone'] = ''

        form = AdminPetForm(data=form_data)

        self.assertFalse(form.is_valid())
        self.assertIn('guest_owner_phone', form.errors)

    def test_walkin_patient_requires_email_address(self):
        form_data = self.form_data.copy()
        form_data['guest_owner_email'] = ''

        form = AdminPetForm(data=form_data)

        self.assertFalse(form.is_valid())
        self.assertIn('guest_owner_email', form.errors)

    def test_walkin_patient_accepts_valid_contact_details(self):
        form = AdminPetForm(data=self.form_data)

        self.assertTrue(form.is_valid(), form.errors)

    def test_walkin_patient_rejects_duplicate_patient_for_same_owner_identity(self):
        existing = AdminPetForm(data=self.form_data)
        self.assertTrue(existing.is_valid(), existing.errors)
        existing.save()

        duplicate_data = self.form_data.copy()
        duplicate_data.update({
            'guest_owner_name': ' walk-in OWNER ',
            'guest_owner_email': 'OWNER@example.com',
            'name': ' buddy ',
        })
        form = AdminPetForm(data=duplicate_data)

        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)
        self.assertIn('same owner details', form.errors['name'][0])

    def test_walkin_patient_allows_another_pet_for_the_same_guest_owner(self):
        existing = AdminPetForm(data=self.form_data)
        self.assertTrue(existing.is_valid(), existing.errors)
        existing.save()

        form_data = self.form_data.copy()
        form_data['name'] = 'Luna'
        form = AdminPetForm(data=form_data)

        self.assertTrue(form.is_valid(), form.errors)

    def test_editing_walkin_patient_allows_unchanged_owner_and_pet_details(self):
        pet = AdminPetForm(data=self.form_data).save()

        form = AdminPetForm(data=self.form_data, instance=pet)

        self.assertTrue(form.is_valid(), form.errors)

    def test_editing_walkin_patient_rejects_matching_another_patient_record(self):
        pet = AdminPetForm(data=self.form_data).save()
        other_pet_data = self.form_data.copy()
        other_pet_data['name'] = 'Luna'
        other_pet = AdminPetForm(data=other_pet_data).save()
        edit_data = self.form_data.copy()
        edit_data['name'] = other_pet.name

        form = AdminPetForm(data=edit_data, instance=pet)

        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)
        self.assertIn('same owner details', form.errors['name'][0])

    def test_walkin_account_creation_rejects_existing_email_during_edit(self):
        get_user_model().objects.create_user(
            username='existing-walkin-email',
            email='owner@example.com',
            password='A-secure-test-password-923!',
        )
        pet = AdminPetForm(data=self.form_data).save()
        form_data = self.form_data.copy()
        form_data['create_new_account'] = 'on'

        form = AdminPetForm(data=form_data, instance=pet)

        self.assertFalse(form.is_valid())
        self.assertIn('guest_owner_email', form.errors)
        self.assertIn('already linked to a portal account', form.errors['guest_owner_email'][0])

    def test_inactive_pet_requires_reason(self):
        form_data = self.form_data.copy()
        form_data['is_active'] = ''

        form = AdminPetForm(data=form_data)

        self.assertFalse(form.is_valid())
        self.assertIn('inactive_reason', form.errors)

    def test_inactive_pet_accepts_reason(self):
        form_data = self.form_data.copy()
        form_data.update({'is_active': '', 'inactive_reason': 'Owner requested profile to be inactive.'})

        form = AdminPetForm(data=form_data)

        self.assertTrue(form.is_valid(), form.errors)
        pet = form.save()
        self.assertFalse(pet.is_active)
        self.assertEqual(pet.inactive_reason, form_data['inactive_reason'])


class PetInactiveReasonFormTests(TestCase):
    def test_portal_form_requires_reason_when_pet_is_inactive(self):
        form = PetForm(data={
            'name': 'Buddy',
            'species': 'Dog',
            'sex': Pet.Sex.MALE,
            'is_active': '',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('inactive_reason', form.errors)

    def test_portal_form_accepts_inactive_pet_with_reason(self):
        form = PetForm(data={
            'name': 'Buddy',
            'species': 'Dog',
            'sex': Pet.Sex.MALE,
            'is_active': '',
            'inactive_reason': 'Owner requested profile to be inactive.',
        })

        self.assertTrue(form.is_valid(), form.errors)
        pet = form.save()
        self.assertFalse(pet.is_active)
        self.assertEqual(pet.inactive_reason, form.cleaned_data['inactive_reason'])


class PortalPetNameUniquenessTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username='pet-name-owner',
            password='test-password',
        )
        self.other_owner = get_user_model().objects.create_user(
            username='other-pet-name-owner',
            password='test-password',
        )
        self.pet = Pet.objects.create(
            owner=self.owner,
            name='Milo',
            species='Dog',
            sex=Pet.Sex.MALE,
        )
        self.form_data = {
            'name': 'Milo',
            'species': 'Dog',
            'sex': Pet.Sex.MALE,
            'is_active': 'on',
        }

    def test_portal_form_rejects_duplicate_name_for_same_owner_case_insensitively(self):
        form_data = self.form_data.copy()
        form_data['name'] = '  mIlO  '

        form = PetForm(data=form_data, user=self.owner)

        self.assertFalse(form.is_valid())
        self.assertIn(
            'You already have a pet with this name. Please enter a different name.',
            form.errors['name'],
        )

    def test_portal_form_allows_same_name_for_another_owner(self):
        form = PetForm(data=self.form_data, user=self.other_owner)

        self.assertTrue(form.is_valid(), form.errors)

    def test_portal_form_allows_keeping_name_when_editing_same_pet(self):
        form = PetForm(data=self.form_data, instance=self.pet, user=self.owner)

        self.assertTrue(form.is_valid(), form.errors)

    @override_settings(STORAGES={
        **settings.STORAGES,
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    })
    def test_add_pet_view_displays_duplicate_name_error(self):
        self.client.force_login(self.owner)

        response = self.client.post(reverse('patients:add_pet'), self.form_data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'You already have a pet with this name. Please enter a different name.',
        )
        self.assertEqual(Pet.objects.filter(owner=self.owner).count(), 1)


class PortalOwnerSearchTests(TestCase):
    def test_branch_restricted_staff_can_search_owner_without_branch_or_patients(self):
        branch = Branch.objects.create(
            name='Search Test Branch',
            phone_number='09123456789',
            address='1 Test Street',
            city='Test City',
            state='Test State',
            zip_code='1000',
        )
        patients_module, _ = Module.objects.get_or_create(
            code=Module.PATIENTS,
            defaults={'name': 'Patients'},
        )
        role = Role.objects.create(
            name='Branch-Restricted Patient Search Role',
            code='branch-restricted-patient-search',
            hierarchy_level=2,
            is_staff_role=True,
        )
        ModulePermission.objects.create(
            role=role,
            module=patients_module,
            permission_type=ModulePermission.PermissionType.CREATE,
            restrict_to_branch=True,
        )
        staff = get_user_model().objects.create_user(
            username='branchstaff',
            email='branchstaff@example.com',
            password='A-secure-test-password-925!',
            branch=branch,
            assigned_role=role,
        )
        owner = get_user_model().objects.create_user(
            username='unassignedowner',
            email='owner@example.com',
            first_name='Unassigned',
            last_name='Owner',
            password='A-secure-test-password-926!',
        )
        client = Client()
        client.force_login(staff)

        response = client.get(
            reverse('patients:api_owner_search'),
            {'q': 'Unassigned Owner'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['owners'][0]['id'], owner.pk)

    def test_owner_search_matches_phone_number(self):
        admin = get_user_model().objects.create_superuser(
            username='patientadmin',
            email='patientadmin@example.com',
            password='A-secure-test-password-923!',
        )
        owner = get_user_model().objects.create_user(
            username='portalowner',
            email='owner@example.com',
            phone_number='09123456789',
            first_name='Portal',
            last_name='Owner',
            password='A-secure-test-password-924!',
        )
        client = Client()
        client.force_login(admin)

        response = client.get(
            reverse('patients:api_owner_search'),
            {'q': '091234'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['owners'][0]['id'], owner.pk)
        self.assertEqual(response.json()['owners'][0]['phone'], '09123456789')

    def test_transfer_owner_search_is_available_to_patient_editors(self):
        admin = get_user_model().objects.create_superuser(
            username='transfer-search-admin',
            email='transfer-search-admin@example.com',
            password='A-secure-test-password-927!',
        )
        owner = get_user_model().objects.create_user(
            username='transfersearchowner',
            email='transfer-owner@example.com',
            first_name='Transfer',
            last_name='Owner',
            password='A-secure-test-password-928!',
        )
        client = Client()
        client.force_login(admin)

        response = client.get(
            reverse('patients:api_transfer_owner_search'),
            {'q': 'Transfer Owner'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['owners'][0]['id'], owner.pk)


class BranchRestrictedPatientListTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name='Patient Scope Branch',
            phone_number='09123456789',
            address='1 Test Street',
            city='Test City',
            state='Test State',
            zip_code='1000',
        )
        module, _ = Module.objects.get_or_create(
            code='patients', defaults={'name': 'Patients'},
        )
        role = Role.objects.create(
            name='Patient Scope Role',
            code='patient-scope-test-role',
            hierarchy_level=4,
        )
        ModulePermission.objects.create(
            role=role,
            module=module,
            permission_type=ModulePermission.PermissionType.VIEW,
            restrict_to_branch=True,
        )
        self.user = get_user_model().objects.create_user(
            username='patient-scope-user', assigned_role=role,
        )
        self.pet = Pet.objects.create(
            name='Branch Pet', species='Dog', sex=Pet.Sex.MALE, branch=self.branch,
        )

    def test_unassigned_branch_restricted_staff_cannot_see_patients_across_branches(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('patients:admin_list'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['branch_assignment_required'])
        self.assertEqual(response.context['pets'].paginator.count, 0)
        self.assertContains(response, 'Ask an administrator to assign your branch')
        self.assertNotContains(response, self.pet.name)

    def test_assigned_branch_restricted_staff_sees_only_their_branch_patients(self):
        self.user.branch = self.branch
        self.user.save(update_fields=['branch'])
        self.client.force_login(self.user)

        response = self.client.get(reverse('patients:admin_list'))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['branch_assignment_required'])
        self.assertEqual(
            [pet.pk for pet in response.context['pets']],
            [self.pet.pk],
        )
        self.assertNotContains(response, 'title="Clear Filters"')

    def test_patient_search_finds_patients_beyond_the_first_page(self):
        Pet.objects.create(
            name='Searchable Page Two Patient',
            species='Dog',
            sex=Pet.Sex.MALE,
            branch=self.branch,
        )
        for index in range(10):
            Pet.objects.create(
                name=f'Newer Patient {index}',
                species='Dog',
                sex=Pet.Sex.MALE,
                branch=self.branch,
            )
        self.user.branch = self.branch
        self.user.save(update_fields=['branch'])
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('patients:admin_list'),
            {'q': 'Searchable Page Two Patient'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['pets'].paginator.count, 1)
        self.assertEqual(
            [pet.name for pet in response.context['pets']],
            ['Searchable Page Two Patient'],
        )

    def test_patient_search_dropdown_finds_patients_beyond_the_first_page(self):
        target = Pet.objects.create(
            name='Remote Dropdown Patient',
            species='Dog',
            sex=Pet.Sex.MALE,
            branch=self.branch,
        )
        for index in range(10):
            Pet.objects.create(
                name=f'Dropdown Newer Patient {index}',
                species='Dog',
                sex=Pet.Sex.MALE,
                branch=self.branch,
            )
        self.user.branch = self.branch
        self.user.save(update_fields=['branch'])
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('patients:api_patient_search'),
            {'q': 'Remote Dropdown Patient'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [patient['id'] for patient in response.json()['patients']],
            [target.pk],
        )

    def test_patient_search_dropdown_respects_branch_restrictions(self):
        other_branch = Branch.objects.create(
            name='Other Patient Search Branch',
            phone_number='09123456780',
            address='2 Test Street',
            city='Test City',
            state='Test State',
            zip_code='1001',
        )
        restricted_patient = Pet.objects.create(
            name='Restricted Search Patient',
            species='Dog',
            sex=Pet.Sex.MALE,
            branch=self.branch,
        )
        Pet.objects.create(
            name='Restricted Search Patient Elsewhere',
            species='Dog',
            sex=Pet.Sex.MALE,
            branch=other_branch,
        )
        self.user.branch = self.branch
        self.user.save(update_fields=['branch'])
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('patients:api_patient_search'),
            {'q': 'Restricted Search Patient'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [patient['id'] for patient in response.json()['patients']],
            [restricted_patient.pk],
        )


class BranchRestrictedWalkInRegistrationTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name='Reception Walk-in Branch',
            phone_number='09123456789',
            address='1 Test Street',
            city='Test City',
            state='Test State',
            zip_code='1000',
        )
        module, _ = Module.objects.get_or_create(
            code='patients', defaults={'name': 'Patients'},
        )
        role = Role.objects.create(
            name='Receptionist Patient Registration Role',
            code='receptionist-patient-registration',
            hierarchy_level=4,
            is_staff_role=True,
        )
        for permission_type in (
            ModulePermission.PermissionType.VIEW,
            ModulePermission.PermissionType.CREATE,
        ):
            ModulePermission.objects.create(
                role=role,
                module=module,
                permission_type=permission_type,
                restrict_to_branch=True,
            )
        self.receptionist = get_user_model().objects.create_user(
            username='walkin-receptionist',
            email='walkin-receptionist@example.com',
            password='A-secure-test-password-927!',
            assigned_role=role,
            branch=self.branch,
        )

    def test_walkin_registration_uses_receptionist_branch_and_branch_filter_finds_pet(self):
        self.client.force_login(self.receptionist)

        response = self.client.post(reverse('patients:admin_add_pet'), {
            'source': Pet.Source.WALKIN,
            'guest_owner_name': 'Walk-in Pet Owner',
            'guest_owner_phone': '09123456789',
            'guest_owner_email': 'walkin-owner@example.com',
            'name': 'Reception Walk-in Patient',
            'species': 'Dog',
            'sex': Pet.Sex.FEMALE,
            'color': 'Brown',
            'is_active': 'on',
        })

        self.assertEqual(response.status_code, 302)
        pet = Pet.objects.get(name='Reception Walk-in Patient')
        self.assertEqual(pet.source, Pet.Source.WALKIN)
        self.assertEqual(pet.branch_id, self.branch.pk)

        admin = get_user_model().objects.create_superuser(
            username='walkin-branch-filter-admin',
            email='walkin-filter-admin@example.com',
            password='A-secure-test-password-928!',
        )
        self.client.force_login(admin)
        response = self.client.get(
            reverse('patients:admin_list'),
            {'branch': self.branch.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, pet.name)

    def test_unrestricted_receptionist_walkin_defaults_to_assigned_branch(self):
        module, _ = Module.objects.get_or_create(
            code='patients', defaults={'name': 'Patients'},
        )
        role = Role.objects.create(
            name='Unrestricted Receptionist Registration Role',
            code='unrestricted-receptionist-registration',
            hierarchy_level=4,
            is_staff_role=True,
        )
        for permission_type in (
            ModulePermission.PermissionType.VIEW,
            ModulePermission.PermissionType.CREATE,
        ):
            ModulePermission.objects.create(
                role=role,
                module=module,
                permission_type=permission_type,
                restrict_to_branch=False,
            )
        receptionist = get_user_model().objects.create_user(
            username='unrestricted-walkin-receptionist',
            email='unrestricted-walkin@example.com',
            password='A-secure-test-password-929!',
            assigned_role=role,
            branch=self.branch,
        )
        self.client.force_login(receptionist)

        response = self.client.post(reverse('patients:admin_add_pet'), {
            'source': Pet.Source.WALKIN,
            'guest_owner_name': 'Unrestricted Walk-in Owner',
            'guest_owner_phone': '09123456789',
            'guest_owner_email': 'unrestricted-owner@example.com',
            'name': 'Unrestricted Walk-in Patient',
            'species': 'Dog',
            'sex': Pet.Sex.MALE,
            'color': 'Black',
            'is_active': 'on',
        })

        self.assertEqual(response.status_code, 302)
        pet = Pet.objects.get(name='Unrestricted Walk-in Patient')
        self.assertEqual(pet.branch_id, self.branch.pk)

        response = self.client.get(
            reverse('patients:admin_list'),
            {'q': pet.name},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['is_branch_restricted'])
        self.assertContains(response, pet.name)

    def test_unfiltered_patient_list_does_not_show_clear_filter_button(self):
        self.client.force_login(self.receptionist)

        response = self.client.get(reverse('patients:admin_list'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'title="Clear Filters"')


@override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }
)
class PetDeleteConfirmationModalTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username='pet-delete-owner',
            email='pet-delete-owner@example.com',
            password='A-secure-test-password-923!',
        )
        self.pet = Pet.objects.create(
            owner=self.owner,
            name='Modal Patient',
            species='Dog',
            sex=Pet.Sex.FEMALE,
        )
        self.client.force_login(self.owner)

    def test_delete_url_redirects_instead_of_showing_confirmation_page(self):
        response = self.client.get(reverse('patients:delete_pet', args=[self.pet.pk]))

        self.assertRedirects(response, reverse('patients:my_pets'))

    def test_owner_pet_pages_do_not_render_pet_delete_controls_or_upcoming_section(self):
        list_response = self.client.get(reverse('patients:my_pets'))
        detail_response = self.client.get(
            reverse('patients:user_pet_detail', args=[self.pet.pk]),
        )

        for response in (list_response, detail_response):
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, 'petDeleteModal')
            self.assertNotContains(response, 'pet-delete-trigger')
            self.assertNotContains(response, 'data-delete-url')
        self.assertNotContains(list_response, 'Upcoming Appointments')

    def test_pet_hero_medical_record_button_opens_latest_record(self):
        MedicalRecord.objects.create(
            pet=self.pet,
            date_recorded='2026-10-10',
        )
        latest_record = MedicalRecord.objects.create(
            pet=self.pet,
            date_recorded='2026-10-20',
        )

        response = self.client.get(
            reverse('patients:user_pet_detail', args=[self.pet.pk]),
        )

        self.assertEqual(response.status_code, 200)
        hero_actions = response.content.decode().split(
            'class="upd-hero-actions"',
            1,
        )[1].split('</div>', 1)[0]
        self.assertIn(
            f'href="{reverse("records:user_detail", args=[latest_record.pk])}"',
            hero_actions,
        )
        self.assertIn('View Medical Record', hero_actions)
        self.assertNotIn('href="#medical-records-section"', hero_actions)

        record_response = self.client.get(
            reverse('records:user_detail', args=[latest_record.pk]),
        )
        self.assertEqual(record_response.status_code, 200)
        self.assertContains(record_response, f"{self.pet.name}'s Records")

    def test_admin_pet_list_does_not_render_delete_controls(self):
        admin = get_user_model().objects.create_superuser(
            username='patient-list-admin',
            email='patient-list-admin@example.com',
            password='A-secure-test-password-923!',
        )
        self.client.force_login(admin)

        response = self.client.get(reverse('patients:admin_list'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'admin_delete_pet')
        self.assertNotContains(response, 'deletePetModal')
        self.assertNotContains(response, 'bx-trash')
