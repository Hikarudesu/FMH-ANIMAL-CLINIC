from django.contrib.auth import authenticate, get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.rbac_models import Role
from branches.models import Branch
from .models import StaffMember


class StaffAccountActivationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='clinicstaff',
            email='staff@example.com',
            password='A-secure-test-password-923!',
        )
        self.staff = StaffMember.objects.create(
            user=self.user,
            first_name='Clinic',
            last_name='Staff',
            position=StaffMember.Position.RECEPTIONIST,
        )

    def test_deactivating_staff_disables_login_and_records_date(self):
        self.staff.set_active(False)

        self.user.refresh_from_db()
        self.staff.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertFalse(self.staff.is_active)
        self.assertIsNotNone(self.staff.inactive_since)
        self.assertIsNone(authenticate(username='clinicstaff', password='A-secure-test-password-923!'))

    def test_reactivating_staff_restores_login_and_clears_inactive_date(self):
        self.staff.set_active(False)
        self.staff.set_active(True)

        self.user.refresh_from_db()
        self.staff.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertTrue(self.staff.is_active)
        self.assertIsNone(self.staff.inactive_since)
        self.assertIsNotNone(authenticate(username='clinicstaff', password='A-secure-test-password-923!'))

    def test_inactive_staff_is_not_schedulable(self):
        self.staff.set_active(False)

        self.assertFalse(
            StaffMember.objects.schedulable_staff().filter(pk=self.staff.pk).exists()
        )


class InactiveStaffListTests(TestCase):
    def test_inactive_tab_filters_by_branch_and_inactive_date(self):
        branch = Branch.objects.create(
            name='Inactive Staff Test Branch',
            phone_number='09123456789',
            address='1 Test Street',
            city='Test City',
            state='Test State',
            zip_code='1000',
        )
        role = Role.objects.create(
            name='Inactive Staff Test Role',
            code='inactive-staff-test',
            hierarchy_level=3,
            is_staff_role=True,
        )
        inactive_user = get_user_model().objects.create_user(
            username='inactiveclinicstaff',
            email='inactive-staff@example.com',
            password='A-secure-test-password-923!',
            assigned_role=role,
            branch=branch,
            is_active=False,
        )
        StaffMember.objects.create(
            user=inactive_user,
            first_name='Inactive',
            last_name='Staff',
            email=inactive_user.email,
            position=StaffMember.Position.RECEPTIONIST,
            branch=branch,
            is_active=False,
            inactive_since=timezone.now(),
        )
        superadmin = get_user_model().objects.create_superuser(
            username='stafflistadmin',
            email='stafflistadmin@example.com',
            password='A-secure-test-password-923!',
        )
        self.client.force_login(superadmin)

        response = self.client.get(reverse('employees:staff_list'), {
            'status': 'inactive',
            'branch': str(branch.pk),
            'inactive_from': timezone.localdate().isoformat(),
            'inactive_to': timezone.localdate().isoformat(),
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'inactiveclinicstaff')
        self.assertEqual(list(response.context['staff_users']), [inactive_user])

    def test_unassigned_staff_profile_remains_visible_and_editable(self):
        user = get_user_model().objects.create_user(
            username='orphanedclinicstaff',
            email='orphaned-staff@example.com',
            password='A-secure-test-password-923!',
        )
        StaffMember.objects.create(
            user=user,
            first_name='Orphaned',
            last_name='Staff',
            email=user.email,
            position=StaffMember.Position.RECEPTIONIST,
        )
        superadmin = get_user_model().objects.create_superuser(
            username='orphanedstaffadmin',
            email='orphanedstaffadmin@example.com',
            password='A-secure-test-password-923!',
        )
        self.client.force_login(superadmin)

        list_response = self.client.get(reverse('employees:staff_list'))
        edit_response = self.client.get(
            reverse('employees:staff_edit', args=[user.pk]),
        )

        self.assertContains(list_response, 'orphanedclinicstaff')
        self.assertEqual(edit_response.status_code, 200)


class RoleDeletionSafetyTests(TestCase):
    def test_role_with_assigned_user_cannot_be_deleted_or_unassign_that_user(self):
        role = Role.objects.create(
            name='Protected Staff Role',
            code='protected-staff-role',
            hierarchy_level=3,
            is_staff_role=True,
        )
        user = get_user_model().objects.create_user(
            username='protectedstaff',
            email='protectedstaff@example.com',
            password='A-secure-test-password-923!',
            assigned_role=role,
        )
        superadmin = get_user_model().objects.create_superuser(
            username='roledeleteadmin',
            email='roledeleteadmin@example.com',
            password='A-secure-test-password-923!',
        )
        self.client.force_login(superadmin)

        response = self.client.post(
            reverse('accounts:role_delete', args=[role.pk]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Role.objects.filter(pk=role.pk).exists())
        user.refresh_from_db()
        self.assertEqual(user.assigned_role_id, role.pk)

    def test_active_unassigned_staff_can_be_found_in_role_management(self):
        user = get_user_model().objects.create_user(
            username='darwin-recovery-test',
            email='darwin-recovery-test@example.com',
            password='A-secure-test-password-923!',
        )
        profile = StaffMember.objects.create(
            user=user,
            first_name='Darwin',
            last_name='Recovery',
            email=user.email,
            position=StaffMember.Position.RECEPTIONIST,
        )
        profile.delete()
        role = Role.objects.create(
            name='Darwin Recovery Role',
            code='darwin-recovery-role',
            hierarchy_level=3,
            is_staff_role=True,
        )
        superadmin = get_user_model().objects.create_superuser(
            username='darwin-recovery-admin',
            email='darwin-recovery-admin@example.com',
            password='A-secure-test-password-923!',
        )
        self.client.force_login(superadmin)

        list_response = self.client.get(reverse('accounts:user_role_list'))
        assign_response = self.client.post(
            reverse('accounts:assign_user_role', args=[user.pk]),
            {'role_id': role.pk},
        )

        self.assertContains(list_response, 'darwin-recovery-test')
        self.assertEqual(assign_response.status_code, 302)
        user.refresh_from_db()
        self.assertEqual(user.assigned_role_id, role.pk)

    def test_inactive_staff_is_hidden_and_cannot_be_role_assigned(self):
        old_role = Role.objects.create(
            name='Inactive User Existing Role',
            code='inactive-user-existing-role',
            hierarchy_level=3,
            is_staff_role=True,
        )
        new_role = Role.objects.create(
            name='Inactive User New Role',
            code='inactive-user-new-role',
            hierarchy_level=4,
            is_staff_role=True,
        )
        user = get_user_model().objects.create_user(
            username='inactive-role-user',
            email='inactive-role-user@example.com',
            password='A-secure-test-password-923!',
            assigned_role=old_role,
            is_active=False,
        )
        superadmin = get_user_model().objects.create_superuser(
            username='inactive-role-admin',
            email='inactive-role-admin@example.com',
            password='A-secure-test-password-923!',
        )
        self.client.force_login(superadmin)

        list_response = self.client.get(reverse('accounts:user_role_list'))
        assign_response = self.client.post(
            reverse('accounts:assign_user_role', args=[user.pk]),
            {'role_id': new_role.pk},
        )

        self.assertNotContains(list_response, 'inactive-role-user')
        self.assertEqual(assign_response.status_code, 302)
        user.refresh_from_db()
        self.assertEqual(user.assigned_role_id, old_role.pk)

    def test_edit_inactive_staff_reuses_soft_deleted_profile(self):
        branch = Branch.objects.create(
            name='Soft Deleted Staff Branch',
            phone_number='09123456789',
            address='1 Test Street',
            city='Test City',
            state='Test State',
            zip_code='1000',
        )
        role = Role.objects.create(
            name='Soft Deleted Staff Role',
            code='soft-deleted-staff-test',
            hierarchy_level=3,
            is_staff_role=True,
        )
        inactive_user = get_user_model().objects.create_user(
            username='softdeletedstaff',
            email='softdeletedstaff@example.com',
            password='A-secure-test-password-923!',
            assigned_role=role,
            branch=branch,
            is_active=False,
        )
        profile = StaffMember.objects.create(
            user=inactive_user,
            first_name='Soft Deleted',
            last_name='Staff',
            email=inactive_user.email,
            position=StaffMember.Position.RECEPTIONIST,
            branch=branch,
            is_active=False,
            inactive_since=timezone.now(),
        )
        profile.delete()
        superadmin = get_user_model().objects.create_superuser(
            username='softdeletedstaffadmin',
            email='softdeletedstaffadmin@example.com',
            password='A-secure-test-password-923!',
        )
        self.client.force_login(superadmin)

        response = self.client.get(
            reverse('employees:staff_edit', args=[inactive_user.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['staff_profile'].pk, profile.pk)