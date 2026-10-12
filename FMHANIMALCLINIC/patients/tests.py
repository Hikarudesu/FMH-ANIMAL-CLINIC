from django.contrib.auth import get_user_model
<<<<<<< HEAD
from django.test import TestCase
=======
from django.test import Client, TestCase
>>>>>>> 1a18aa4ad53c5006883f90863d1c0f5e47d10299
from django.urls import reverse

from accounts.rbac_models import Module, ModulePermission, Role
from branches.models import Branch
<<<<<<< HEAD
from patients.models import Pet


class BranchRestrictedPatientListTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name='Patient Scope Branch',
=======
from .forms import AdminPetForm


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


class PortalOwnerSearchTests(TestCase):
    def test_branch_restricted_staff_can_search_owner_without_branch_or_patients(self):
        branch = Branch.objects.create(
            name='Search Test Branch',
>>>>>>> 1a18aa4ad53c5006883f90863d1c0f5e47d10299
            phone_number='09123456789',
            address='1 Test Street',
            city='Test City',
            state='Test State',
            zip_code='1000',
        )
<<<<<<< HEAD
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
=======
        patients_module, _ = Module.objects.get_or_create(
            code=Module.PATIENTS,
            defaults={'name': 'Patients'},
        )
        role = Role.objects.create(
            name='Branch-Restricted Patient Search Role',
            code='branch-restricted-patient-search',
            hierarchy_level=4,
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
>>>>>>> 1a18aa4ad53c5006883f90863d1c0f5e47d10299
