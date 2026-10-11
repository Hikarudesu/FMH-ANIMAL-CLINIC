import re
from datetime import time
from urllib.parse import parse_qs, urlsplit

from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.core import mail
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.activity_context import reset_current_actor, set_current_actor
from accounts.models import ActivityLog
from accounts.rbac_models import Module, ModulePermission, Role, SpecialPermission
from branches.models import Branch
from appointments.models import Appointment
from billing.models import CustomerStatement
from employees.models import StaffMember
from .forms import PetOwnerRegistrationForm
from .lifecycle import (
    expire_due_owner_accounts,
    resolve_owner_deactivation_on_login,
    schedule_owner_deactivation,
)


class RolePermissionManagementTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username='rbac-test-admin',
            email='rbac-test-admin@example.com',
            password='A-secure-test-password-923!',
        )
        self.role = Role.objects.create(
            name='RBAC Editable Role',
            code='rbac-editable-role',
            hierarchy_level=4,
        )
        self.inventory, _ = Module.objects.get_or_create(
            code='inventory', defaults={'name': 'Inventory'},
        )
        self.transfers, _ = Module.objects.get_or_create(
            code='stock_transfers', defaults={'name': 'Stock Transfers'},
        )
        self.stock_monitor, _ = SpecialPermission.objects.get_or_create(
            code='can_access_stock_monitor',
            defaults={'name': 'Access Stock Monitor'},
        )

    def test_manage_grants_each_module_action(self):
        ModulePermission.objects.create(
            role=self.role,
            module=self.inventory,
            permission_type=ModulePermission.PermissionType.MANAGE,
        )

        for permission in ('VIEW', 'CREATE', 'EDIT', 'DELETE', 'MANAGE'):
            with self.subTest(permission=permission):
                self.assertTrue(
                    self.role.has_module_permission('inventory', permission)
                )

    def test_role_edit_exposes_manage_and_preserves_hidden_permissions(self):
        ModulePermission.objects.create(
            role=self.role,
            module=self.transfers,
            permission_type=ModulePermission.PermissionType.VIEW,
        )
        self.client.force_login(self.admin)

        edit_url = reverse('accounts:role_edit', args=[self.role.pk])
        self.assertContains(self.client.get(edit_url), 'perm_inventory_MANAGE')

        response = self.client.post(edit_url, {
            'name': self.role.name,
            'description': self.role.description,
            'perm_inventory_MANAGE': 'on',
            'special_can_access_stock_monitor': 'on',
        })

        self.assertEqual(response.status_code, 302)
        self.role.refresh_from_db()
        self.assertTrue(self.role.has_module_permission('stock_transfers', 'VIEW'))
        self.assertTrue(self.role.has_module_permission('inventory', 'CREATE'))
        self.assertTrue(
            self.role.special_permissions.filter(permission=self.stock_monitor).exists()
        )

    def test_profile_updates_sync_appointments_and_customer_statements(self):
        branch = Branch.objects.create(
            name='Profile Sync Branch',
            phone_number='09123456789',
            address='1 Profile Street',
            city='Manila',
            state='NCR',
            zip_code='1000',
        )
        owner = get_user_model().objects.create_user(
            username='profile-sync-owner',
            first_name='Before',
            last_name='Profile',
            email='before@example.com',
            phone_number='09123456789',
            address='Old Address',
            password='A-secure-test-password-923!',
        )
        appointment = Appointment.objects.create(
            owner_name='Before Profile',
            owner_email=owner.email,
            owner_phone=owner.phone_number,
            owner_address=owner.address,
            pet_name='Profile Pet',
            branch=branch,
            appointment_date=timezone.localdate(),
            appointment_time=time(9, 0),
            user=owner,
            source=Appointment.Source.PORTAL,
        )
        statement = CustomerStatement.objects.create(
            patient_name='Profile Pet',
            owner_name='Before Profile',
            customer=owner,
            date=timezone.localdate(),
        )

        owner.first_name = 'After'
        owner.last_name = 'Updated'
        owner.email = 'after@example.com'
        owner.phone_number = '09987654321'
        owner.address = 'New Address'
        owner.save()

        appointment.refresh_from_db()
        statement.refresh_from_db()
        self.assertEqual(appointment.owner_name, 'After Updated')
        self.assertEqual(appointment.owner_email, 'after@example.com')
        self.assertEqual(appointment.owner_phone, '09987654321')
        self.assertEqual(appointment.owner_address, 'New Address')
        self.assertEqual(statement.owner_name, 'After Updated')

    def test_staff_account_profile_updates_sync_linked_staff_records(self):
        branch = Branch.objects.create(
            name='Staff Sync Branch',
            phone_number='09123456789',
            address='1 Staff Street',
            city='Manila',
            state='NCR',
            zip_code='1000',
        )
        staff_roles = (
            ('veterinarian', StaffMember.Position.VETERINARIAN),
            ('assistant_veterinarian', StaffMember.Position.VET_ASSISTANT),
            ('cashier', StaffMember.Position.RECEPTIONIST),
        )

        for role_code, position in staff_roles:
            with self.subTest(role_code=role_code):
                role, _ = Role.objects.get_or_create(
                    code=role_code,
                    defaults={
                        'name': role_code.replace('_', ' ').title(),
                        'hierarchy_level': 5,
                        'is_staff_role': True,
                    },
                )
                user = get_user_model().objects.create_user(
                    username=f'{role_code}-profile-sync',
                    first_name='Before',
                    last_name='Staff',
                    email=f'{role_code}@example.com',
                    phone_number='09123456789',
                    password='A-secure-test-password-923!',
                    assigned_role=role,
                    branch=branch,
                )
                staff = StaffMember.objects.create(
                    first_name=user.first_name,
                    last_name=user.last_name,
                    email=user.email,
                    phone=user.phone_number,
                    branch=branch,
                    position=position,
                    user=user,
                )

                user.first_name = 'After'
                user.last_name = 'Updated'
                user.email = f'updated-{role_code}@example.com'
                user.phone_number = '09987654321'
                user.branch = branch
                user.save()

                staff.refresh_from_db()
                self.assertEqual(staff.first_name, 'After')
                self.assertEqual(staff.last_name, 'Updated')
                self.assertEqual(staff.email, f'updated-{role_code}@example.com')
                self.assertEqual(staff.phone, '09987654321')
                self.assertEqual(staff.branch_id, branch.pk)

        admin = get_user_model().objects.create_superuser(
            username='admin-profile-sync',
            first_name='Before',
            last_name='Admin',
            email='admin@example.com',
            password='A-secure-test-password-923!',
        )
        admin.branch = branch
        admin.save()
        admin_staff = StaffMember.objects.create(
            first_name=admin.first_name,
            last_name=admin.last_name,
            email=admin.email,
            phone='',
            branch=branch,
            position=StaffMember.Position.ADMIN,
            user=admin,
        )

        admin.first_name = 'After'
        admin.last_name = 'Updated'
        admin.email = 'updated-admin@example.com'
        admin.phone_number = '09987654321'
        admin.save()

        admin_staff.refresh_from_db()
        self.assertEqual(admin_staff.first_name, 'After')
        self.assertEqual(admin_staff.last_name, 'Updated')
        self.assertEqual(admin_staff.email, 'updated-admin@example.com')
        self.assertEqual(admin_staff.phone, '09987654321')
        self.assertEqual(admin_staff.branch_id, branch.pk)

    def test_generic_audit_records_changed_fields_without_values(self):
        branch = Branch.objects.create(
            name='Audit Before',
            phone_number='09123456789',
            address='1 Audit Street',
            city='Test City',
            state='Test State',
            zip_code='1000',
        )
        token = set_current_actor(self.admin)
        try:
            branch.name = 'Audit After'
            branch.save(update_fields=['name'])
        finally:
            reset_current_actor(token)

        update_log = ActivityLog.objects.get(
            object_type='Branch',
            object_id=branch.pk,
            action_type=ActivityLog.ActionType.UPDATE,
        )
        self.assertIn('Changed fields: name', update_log.details)
        self.assertNotIn('Audit Before', update_log.details)
        self.assertNotIn('Audit After', update_log.details)

    def test_module_permission_creation_and_deletion_are_audited(self):
        token = set_current_actor(self.admin)
        try:
            permission = ModulePermission.objects.create(
                role=self.role,
                module=self.inventory,
                permission_type=ModulePermission.PermissionType.VIEW,
            )
            permission_id = permission.pk
            permission.delete()
        finally:
            reset_current_actor(token)

        permission_logs = ActivityLog.objects.filter(
            object_type='ModulePermission',
            object_id=permission_id,
        )
        self.assertTrue(permission_logs.filter(
            action_type=ActivityLog.ActionType.CREATE,
        ).exists())
        self.assertTrue(permission_logs.filter(
            action_type=ActivityLog.ActionType.DELETE,
        ).exists())


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class RegistrationEmailVerificationTests(TestCase):
    def registration_data(self, email):
        return {
            'username': 'newpetowner',
            'first_name': 'New',
            'last_name': 'Owner',
            'email': email,
            'phone_number': '09123456789',
            'address': '',
            'password1': 'A-secure-test-password-923!',
            'password2': 'A-secure-test-password-923!',
            'terms': 'on',
        }

    def test_registration_sends_verify_now_link_and_link_verifies_email(self):
        response = self.client.post(
            reverse('accounts:register_page'),
            self.registration_data('owner@example.com'),
        )

        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(username='newpetowner')
        self.assertFalse(user.email_verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['owner@example.com'])
        self.assertIn('Verify now', mail.outbox[0].alternatives[0][0])

        verification_url = re.search(r'https?://\S+', mail.outbox[0].body).group(0)
        token = parse_qs(urlsplit(verification_url).query)['token'][0]
        response = self.client.get(reverse('accounts:verify_email'), {'token': token})

        user.refresh_from_db()
        self.assertTrue(user.email_verified)
        self.assertEqual(response.status_code, 302)

    def test_registration_rejects_case_insensitive_duplicate_email(self):
        get_user_model().objects.create_user(
            username='existingowner',
            email='owner@example.com',
            password='A-secure-test-password-923!',
        )
        form = PetOwnerRegistrationForm(
            self.registration_data('OWNER@example.com')
        )

        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_profile_email_edit_checks_existing_addresses_case_insensitively(self):
        existing_user = get_user_model().objects.create_user(
            username='existingowner',
            email='owner@example.com',
            password='A-secure-test-password-923!',
        )
        editing_user = get_user_model().objects.create_user(
            username='editingowner',
            email='editing@example.com',
            password='A-secure-test-password-923!',
        )
        from .forms import UserProfileUpdateForm

        form = UserProfileUpdateForm(
            data={
                'username': editing_user.username,
                'first_name': '',
                'last_name': '',
                'email': existing_user.email.upper(),
                'phone_number': '',
                'address': '',
                'branch': '',
            },
            instance=editing_user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_new_users_are_unverified_by_default(self):
        user = get_user_model().objects.create_user(
            username='pendingowner',
            email='pending@example.com',
            password='A-secure-test-password-923!',
        )

        self.assertFalse(user.email_verified)

    def test_database_rejects_case_insensitive_duplicate_emails(self):
        get_user_model().objects.create_user(
            username='existingowner',
            email='owner@example.com',
            password='A-secure-test-password-923!',
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                get_user_model().objects.create_user(
                    username='duplicateowner',
                    email='OWNER@example.com',
                    password='A-secure-test-password-923!',
                )


class OwnerAccountDeactivationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='petowner',
            email='petowner@example.com',
            password='A-secure-test-password-923!',
        )

    def test_owner_has_one_month_to_cancel_by_logging_in(self):
        now = timezone.now()
        schedule_owner_deactivation(self.user, now=now)

        self.user.refresh_from_db()
        self.assertEqual(
            self.user.owner_deactivation_due_at,
            now + relativedelta(months=1),
        )
        self.assertEqual(resolve_owner_deactivation_on_login(self.user, now=now + relativedelta(days=2)), 'cancelled')

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertIsNone(self.user.owner_deactivation_due_at)

    def test_due_owner_is_deactivated_but_account_is_retained(self):
        now = timezone.now()
        self.user.owner_deactivation_requested_at = now - relativedelta(months=1)
        self.user.owner_deactivation_due_at = now - relativedelta(seconds=1)
        self.user.save(update_fields=[
            'owner_deactivation_requested_at',
            'owner_deactivation_due_at',
        ])

        self.assertEqual(expire_due_owner_accounts(now=now), 1)

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertEqual(self.user.owner_account_deactivated_at, now)
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())

    def test_overdue_login_expires_instead_of_cancelling(self):
        now = timezone.now()
        self.user.owner_deactivation_due_at = now - relativedelta(seconds=1)
        self.user.save(update_fields=['owner_deactivation_due_at'])

        self.assertEqual(resolve_owner_deactivation_on_login(self.user, now=now), 'expired')
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_profile_request_schedules_account_deactivation(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('accounts:request_owner_deactivation'),
            {'confirm_deactivation': 'on'},
        )

        self.user.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.user.is_active)
        self.assertIsNotNone(self.user.owner_deactivation_due_at)

    def test_pet_owner_login_before_due_date_cancels_schedule(self):
        schedule_owner_deactivation(self.user)

        response = self.client.post(reverse('accounts:login_page'), {
            'username': self.user.username,
            'password': 'A-secure-test-password-923!',
        })

        self.user.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.user.is_active)
        self.assertIsNone(self.user.owner_deactivation_due_at)

    def test_superadmin_archive_displays_retained_pet_and_medical_record(self):
        from patients.models import Pet
        from records.models import MedicalRecord

        now = timezone.now()
        self.user.is_active = False
        self.user.owner_account_deactivated_at = now
        self.user.save(update_fields=['is_active', 'owner_account_deactivated_at'])
        pet = Pet.objects.create(
            owner=self.user,
            name='Archive Companion',
            species='Dog',
            sex=Pet.Sex.MALE,
        )
        MedicalRecord.objects.bulk_create([
            MedicalRecord(pet=pet, date_recorded=now.date()),
        ])
        superadmin = get_user_model().objects.create_superuser(
            username='archiveadmin',
            email='archiveadmin@example.com',
            password='A-secure-test-password-923!',
        )
        self.client.force_login(superadmin)

        response = self.client.get(reverse('accounts:owner_archive'), {'q': 'Archive Companion'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pet Owner Archive')
        self.assertContains(response, 'Archive Companion')
        self.assertContains(response, 'Medical record')
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())


class BrowserLoginLockoutTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='loginowner',
            email='loginowner@example.com',
            password='A-secure-test-password-923!',
        )

    def test_five_failures_lock_only_the_current_browser(self):
        browser = Client()
        login_url = reverse('accounts:login_page')

        for attempt in range(5):
            response = browser.post(login_url, {
                'username': f'wrong-user-{attempt}',
                'password': 'wrong-password',
            })
            self.assertEqual(response.status_code, 200)

        blocked_response = browser.post(login_url, {
            'username': self.user.username,
            'password': 'A-secure-test-password-923!',
        })
        self.assertEqual(blocked_response.status_code, 200)
        self.assertNotIn('_auth_user_id', browser.session)

        another_browser = Client()
        allowed_response = another_browser.post(login_url, {
            'username': self.user.username,
            'password': 'A-secure-test-password-923!',
        })
        self.assertEqual(allowed_response.status_code, 302)
        self.assertEqual(
            another_browser.session.get('_auth_user_id'), str(self.user.pk),
        )

    def test_first_browser_lock_expires_after_one_minute(self):
        from datetime import timedelta
        from unittest.mock import patch

        from django.utils import timezone

        now = timezone.now()
        browser = Client()
        login_url = reverse('accounts:login_page')

        with patch('accounts.views.timezone.now', return_value=now):
            for _ in range(5):
                browser.post(login_url, {
                    'username': self.user.username,
                    'password': 'wrong-password',
                })

        with patch(
            'accounts.views.timezone.now',
            return_value=now + timedelta(minutes=1, seconds=1),
        ):
            response = browser.post(login_url, {
                'username': self.user.username,
                'password': 'A-secure-test-password-923!',
            })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(browser.session.get('_auth_user_id'), str(self.user.pk))

    def test_lockout_increases_to_five_and_fifteen_minutes_then_caps(self):
        from datetime import timedelta
        from unittest.mock import patch

        from django.utils import timezone

        browser = Client()
        login_url = reverse('accounts:login_page')
        now = timezone.now()

        for expected_seconds in (60, 5 * 60, 15 * 60, 15 * 60):
            with patch('accounts.views.timezone.now', return_value=now):
                for _ in range(5):
                    response = browser.post(login_url, {
                        'username': 'wrong-user',
                        'password': 'wrong-password',
                    })
                    self.assertEqual(response.status_code, 200)

            lock_until = browser.session['login_locked_until']
            self.assertEqual(
                int(float(lock_until) - now.timestamp()),
                expected_seconds,
            )
            now += timedelta(seconds=expected_seconds + 1)

        with patch('accounts.views.timezone.now', return_value=now):
            response = browser.post(login_url, {
                'username': self.user.username,
                'password': 'A-secure-test-password-923!',
            })

        self.assertEqual(response.status_code, 302)
        self.assertNotIn('login_lockout_level', browser.session)