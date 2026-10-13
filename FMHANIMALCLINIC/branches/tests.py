from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from branches.admin import BranchAdmin
from branches.models import Branch
from employees.models import StaffMember
from inventory.models import Product


class BranchStatusManagementTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username='branch-status-admin',
            email='branch-status-admin@example.com',
            password='A-secure-test-password-923!',
        )
        self.active_branch = self.create_branch('Active Test Branch', is_active=True)
        self.inactive_branch = self.create_branch('Inactive Test Branch', is_active=False)
        self.client.force_login(self.admin)

    def create_branch(self, name, *, is_active):
        return Branch.objects.create(
            name=name,
            phone_number='09123456789',
            address='1 Test Street',
            city='Manila',
            state='Metro Manila',
            zip_code='1000',
            is_active=is_active,
        )

    def test_branch_list_tabs_filter_active_and_inactive_branches(self):
        active_response = self.client.get(reverse('branches:list'), {'status': 'active'})
        inactive_response = self.client.get(reverse('branches:list'), {'status': 'inactive'})

        self.assertEqual(active_response.status_code, 200)
        self.assertEqual(inactive_response.status_code, 200)
        self.assertEqual(list(active_response.context['branches']), [self.active_branch])
        self.assertEqual(list(inactive_response.context['branches']), [self.inactive_branch])
        self.assertEqual(active_response.context['active_count'], 1)
        self.assertEqual(active_response.context['inactive_count'], 1)
        self.assertContains(active_response, 'Active Branches')
        self.assertContains(active_response, 'Inactive Branches')
        self.assertContains(active_response, 'Make branch inactive')
        self.assertContains(inactive_response, 'Reactivate branch')
        self.assertContains(active_response, 'Are you sure you want to make this branch inactive?')
        self.assertContains(active_response, 'Are you really sure?')
        self.assertNotContains(active_response, 'openDeleteModal')

    def test_branch_create_and_edit_forms_do_not_expose_active_checkbox(self):
        create_response = self.client.get(reverse('branches:add'))
        edit_response = self.client.get(
            reverse('branches:edit', args=[self.active_branch.pk]),
        )

        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(edit_response.status_code, 200)
        self.assertNotContains(create_response, 'name="is_active"')
        self.assertNotContains(edit_response, 'name="is_active"')

    def test_deactivation_requires_confirmation(self):
        response = self.client.post(
            reverse('branches:toggle_status', args=[self.active_branch.pk]),
        )

        self.assertEqual(response.status_code, 302)
        self.active_branch.refresh_from_db()
        self.assertTrue(self.active_branch.is_active)
        warning_response = self.client.get(response['Location'])
        self.assertContains(warning_response, 'Complete both confirmations to make this branch inactive.')

    def test_one_confirmation_is_not_enough_to_deactivate_branch(self):
        response = self.client.post(
            reverse('branches:toggle_status', args=[self.active_branch.pk]),
            {'confirm_deactivation': 'on'},
        )

        self.assertEqual(response.status_code, 302)
        self.active_branch.refresh_from_db()
        self.assertTrue(self.active_branch.is_active)

    def test_confirmed_deactivation_detaches_accounts_and_preserves_branch_inventory(self):
        user = get_user_model().objects.create_user(
            username='branch-owner-test',
            email='branch-owner-test@example.com',
            password='A-secure-test-password-923!',
            branch=self.active_branch,
        )
        staff = StaffMember.objects.create(
            user=user,
            first_name='Branch',
            last_name='Staff',
            email=user.email,
            position=StaffMember.Position.RECEPTIONIST,
            branch=self.active_branch,
        )
        product = Product.objects.create(
            branch=self.active_branch,
            item_type='Product',
            name='Retained Inactive Branch Product',
            price=25,
            stock_quantity=6,
        )

        response = self.client.post(
            reverse('branches:toggle_status', args=[self.active_branch.pk]),
            {
                'confirm_deactivation': 'on',
                'confirm_deactivation_final': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/branches/?status=inactive')
        self.active_branch.refresh_from_db()
        user.refresh_from_db()
        staff.refresh_from_db()
        self.assertFalse(self.active_branch.is_active)
        self.assertIsNone(user.branch_id)
        self.assertIsNone(staff.branch_id)
        self.assertTrue(Product.objects.filter(pk=product.pk).exists())
        self.assertTrue(Branch.objects.filter(pk=self.active_branch.pk).exists())

    def test_branch_cannot_be_hard_deleted_from_app_or_django_admin(self):
        with self.assertRaises(NoReverseMatch):
            reverse('branches:delete', args=[self.active_branch.pk])

        model_admin = BranchAdmin(Branch, admin.site)
        request = RequestFactory().get('/admin/branches/branch/')
        self.assertFalse(model_admin.has_delete_permission(request, self.active_branch))

    def test_confirmed_deactivation_moves_branch_to_inactive_tab(self):
        response = self.client.post(
            reverse('branches:toggle_status', args=[self.active_branch.pk]),
            {
                'confirm_deactivation': 'on',
                'confirm_deactivation_final': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/branches/?status=inactive')
        self.active_branch.refresh_from_db()
        self.assertFalse(self.active_branch.is_active)

        inactive_response = self.client.get(reverse('branches:list'), {'status': 'inactive'})
        self.assertEqual(list(inactive_response.context['branches']), [self.active_branch, self.inactive_branch])

    def test_inactive_branch_can_be_reactivated_without_deactivation_confirmation(self):
        response = self.client.post(
            reverse('branches:toggle_status', args=[self.inactive_branch.pk]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/branches/?status=active')
        self.inactive_branch.refresh_from_db()
        self.assertTrue(self.inactive_branch.is_active)

    def test_inactive_branches_are_excluded_from_archive_and_payroll_dropdowns(self):
        active_branch = self.create_branch('Alpha Branch', is_active=True)
        other_active_branch = self.create_branch('Bravo Branch', is_active=True)
        inactive_branch = self.create_branch('Charlie Branch', is_active=False)

        archive_response = self.client.get(reverse('accounts:owner_archive'))
        archive_branches = list(archive_response.context['branches'])
        self.assertIn(self.active_branch, archive_branches)
        self.assertIn(active_branch, archive_branches)
        self.assertIn(other_active_branch, archive_branches)
        self.assertNotIn(inactive_branch, archive_branches)
        self.assertNotIn(self.inactive_branch, archive_branches)

        payroll_response = self.client.get(reverse('payroll:vets'))
        payroll_branches = list(payroll_response.context['branches'])
        self.assertIn(self.active_branch, payroll_branches)
        self.assertIn(active_branch, payroll_branches)
        self.assertIn(other_active_branch, payroll_branches)
        self.assertNotIn(inactive_branch, payroll_branches)
        self.assertNotIn(self.inactive_branch, payroll_branches)