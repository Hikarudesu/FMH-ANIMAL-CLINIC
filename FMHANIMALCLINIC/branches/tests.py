from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from branches.models import Branch


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
        self.assertContains(warning_response, 'Confirm that you want to make this branch inactive.')

    def test_confirmed_deactivation_moves_branch_to_inactive_tab(self):
        response = self.client.post(
            reverse('branches:toggle_status', args=[self.active_branch.pk]),
            {'confirm_deactivation': 'on'},
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