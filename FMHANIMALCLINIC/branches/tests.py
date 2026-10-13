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

    def branch_update_data(self, *, confirmed=False):
        data = {
            'name': self.active_branch.name,
            'branch_code': '',
            'clinic_license_number': '',
            'phone_number': self.active_branch.phone_number,
            'email': '',
            'address': self.active_branch.address,
            'city': self.active_branch.city,
            'state': self.active_branch.state,
            'zip_code': self.active_branch.zip_code,
            'operating_hours': '',
            'is_active': '',
            'google_maps_embed_url': '',
            'google_maps_link': '',
            'facebook_url': '',
            'instagram_url': '',
            'messenger_url': '',
            'tiktok_url': '',
            'display_order': '0',
            'badge_label': '',
        }
        if confirmed:
            data['confirm_deactivation'] = 'on'
        return data

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

    def test_deactivation_requires_confirmation_and_confirmation_modal_is_rendered(self):
        edit_url = reverse('branches:edit', args=[self.active_branch.pk])
        edit_response = self.client.get(edit_url)
        self.assertContains(edit_response, 'branchDeactivationModal')
        self.assertContains(edit_response, 'Are you sure you want to make')

        response = self.client.post(edit_url, self.branch_update_data())

        self.assertEqual(response.status_code, 200)
        self.active_branch.refresh_from_db()
        self.assertTrue(self.active_branch.is_active)
        self.assertContains(response, 'Confirm that you want to make this branch inactive.')

    def test_confirmed_deactivation_moves_branch_to_inactive_tab(self):
        response = self.client.post(
            reverse('branches:edit', args=[self.active_branch.pk]),
            self.branch_update_data(confirmed=True),
        )

        self.assertEqual(response.status_code, 302)
        self.active_branch.refresh_from_db()
        self.assertFalse(self.active_branch.is_active)

        inactive_response = self.client.get(reverse('branches:list'), {'status': 'inactive'})
        self.assertEqual(list(inactive_response.context['branches']), [self.active_branch, self.inactive_branch])