from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.rbac_models import Module, ModulePermission, Role
from branches.models import Branch
from patients.models import Pet


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