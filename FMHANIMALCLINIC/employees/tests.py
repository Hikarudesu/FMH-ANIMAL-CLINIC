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