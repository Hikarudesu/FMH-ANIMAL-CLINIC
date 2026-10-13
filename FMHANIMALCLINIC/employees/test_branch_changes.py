from datetime import time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.conf import settings
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.rbac_models import Role, SpecialPermission, SpecialPermissionCodes
from appointments.models import Appointment
from branches.models import Branch
from employees.branch_changes import apply_staff_branch_change
from employees.models import RecurringSchedule, StaffMember, VetSchedule
from notifications.models import Notification


class StaffBranchChangeTests(TestCase):
    def setUp(self):
        self.old_branch = self.create_branch('Point One')
        self.new_branch = self.create_branch('Point Two')
        self.admin = get_user_model().objects.create_superuser(
            username='branch-change-admin',
            email='branch-change-admin@example.com',
            password='A-secure-test-password-923!',
        )

    def create_branch(self, name):
        return Branch.objects.create(
            name=name,
            phone_number='09123456789',
            address='1 Test Street',
            city='Manila',
            state='Metro Manila',
            zip_code='1000',
        )

    def create_role(self, code, special_codes=()):
        role, _ = Role.objects.get_or_create(
            code=code,
            defaults={
                'name': code.replace('_', ' ').title(),
                'hierarchy_level': 4,
                'is_staff_role': True,
            },
        )
        for special_code in special_codes:
            permission = SpecialPermission.objects.get(code=special_code)
            role.special_permissions.get_or_create(permission=permission)
        return role

    def create_staff(self, username, role_code, branch, position, special_codes=()):
        role = self.create_role(role_code, special_codes)
        user = get_user_model().objects.create_user(
            username=username,
            email=f'{username}@example.com',
            password='A-secure-test-password-923!',
            first_name=username.title(),
            last_name='Staff',
            phone_number='09123456789',
            branch=branch,
            assigned_role=role,
        )
        staff = StaffMember.objects.create(
            user=user,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            phone=user.phone_number,
            branch=branch,
            position=position,
        )
        return user, staff

    def profile_data(self, user, branch):
        return {
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'phone_number': user.phone_number,
            'address': user.address,
            'branch': str(branch.pk),
        }

    def test_permanent_position_permission_is_seeded_and_profile_branch_is_locked(self):
        permission = SpecialPermission.objects.get(
            code=SpecialPermissionCodes.PERMANENT_POSITION,
        )
        self.client.force_login(self.admin)
        role_form_response = self.client.get(reverse('accounts:role_create'))
        self.assertContains(role_form_response, 'name="special_permanent_position"')
        self.assertContains(role_form_response, 'Permanent Position')

        role_create_response = self.client.post(
            reverse('accounts:role_create'),
            {
                'name': 'Permanent Position UI Test Role',
                'hierarchy_level': '4',
                'special_permanent_position': 'on',
            },
        )
        self.assertEqual(role_create_response.status_code, 302)
        created_role = Role.objects.get(code='permanent_position_ui_test_role')
        self.assertTrue(
            created_role.special_permissions.filter(permission=permission).exists()
        )

        user, staff = self.create_staff(
            'permanent-staff',
            'permanent-position-test-role',
            self.old_branch,
            StaffMember.Position.RECEPTIONIST,
            (permission.code,),
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse('accounts:profile'),
            self.profile_data(user, self.new_branch),
        )

        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        staff.refresh_from_db()
        self.assertEqual(user.branch_id, self.old_branch.pk)
        self.assertEqual(staff.branch_id, self.old_branch.pk)

    def test_staff_edit_cannot_change_permanent_position_branch(self):
        user, staff = self.create_staff(
            'admin-locked-staff',
            'staff-edit-permanent-test-role',
            self.old_branch,
            StaffMember.Position.RECEPTIONIST,
            (SpecialPermissionCodes.PERMANENT_POSITION,),
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('employees:staff_edit', args=[user.pk]),
            {
                'branch': str(self.new_branch.pk),
                'is_active': 'on',
            },
            follow=True,
        )

        user.refresh_from_db()
        staff.refresh_from_db()
        self.assertEqual(user.branch_id, self.old_branch.pk)
        self.assertEqual(staff.branch_id, self.old_branch.pk)
        self.assertContains(response, 'Permanent Position')

    def test_profile_change_moves_future_and_recurring_schedules_only_with_permission(self):
        user, staff = self.create_staff(
            'schedule-owner',
            'schedule-owner-test-role',
            self.old_branch,
            StaffMember.Position.VETERINARIAN,
            (SpecialPermissionCodes.MANAGE_OWN_SCHEDULE,),
        )
        today = timezone.localdate()
        future_schedule = VetSchedule.objects.create(
            staff=staff,
            branch=self.old_branch,
            date=today + timedelta(days=7),
            start_time=time(9),
            end_time=time(12),
        )
        past_schedule = VetSchedule.objects.create(
            staff=staff,
            branch=self.old_branch,
            date=today - timedelta(days=1),
            start_time=time(9),
            end_time=time(12),
        )
        recurring_schedule = RecurringSchedule.objects.create(
            staff=staff,
            branch=self.old_branch,
            day_of_week=RecurringSchedule.DayOfWeek.MONDAY,
            start_time=time(9),
            end_time=time(12),
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse('accounts:profile'),
            self.profile_data(user, self.new_branch),
        )

        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        staff.refresh_from_db()
        future_schedule.refresh_from_db()
        past_schedule.refresh_from_db()
        recurring_schedule.refresh_from_db()
        self.assertEqual(user.branch_id, self.new_branch.pk)
        self.assertEqual(staff.branch_id, self.new_branch.pk)
        self.assertEqual(future_schedule.branch_id, self.new_branch.pk)
        self.assertEqual(past_schedule.branch_id, self.old_branch.pk)
        self.assertEqual(recurring_schedule.branch_id, self.new_branch.pk)

    def test_current_day_schedule_moves_to_new_branch(self):
        user, staff = self.create_staff(
            'today-schedule-owner',
            'today-schedule-owner-role',
            self.old_branch,
            StaffMember.Position.VETERINARIAN,
            (SpecialPermissionCodes.MANAGE_OWN_SCHEDULE,),
        )
        schedule = VetSchedule.objects.create(
            staff=staff,
            branch=self.old_branch,
            date=timezone.localdate(),
            start_time=time(8),
            end_time=time(12),
            notes='Current day coverage',
        )

        apply_staff_branch_change(user, self.old_branch.pk, self.new_branch)

        schedule.refresh_from_db()
        self.assertEqual(schedule.branch_id, self.new_branch.pk)
        self.assertEqual(schedule.notes, 'Current day coverage')

    def test_current_day_schedule_collision_merges_without_losing_schedule_data(self):
        user, staff = self.create_staff(
            'today-schedule-collision-owner',
            'today-schedule-collision-role',
            self.old_branch,
            StaffMember.Position.VETERINARIAN,
            (SpecialPermissionCodes.MANAGE_OWN_SCHEDULE,),
        )
        old_schedule = VetSchedule.objects.create(
            staff=staff,
            branch=self.old_branch,
            date=timezone.localdate(),
            start_time=time(8),
            end_time=time(10),
            is_available=True,
            notes='Moved coverage',
        )
        destination_schedule = VetSchedule.objects.create(
            staff=staff,
            branch=self.new_branch,
            date=timezone.localdate(),
            start_time=time(8),
            end_time=time(12),
            is_available=False,
            notes='Existing destination coverage',
        )

        apply_staff_branch_change(user, self.old_branch.pk, self.new_branch)

        destination_schedule.refresh_from_db()
        self.assertEqual(destination_schedule.end_time, time(12))
        self.assertTrue(destination_schedule.is_available)
        self.assertIn('Moved coverage', destination_schedule.notes)
        self.assertIn('Existing destination coverage', destination_schedule.notes)
        self.assertFalse(VetSchedule.objects.filter(pk=old_schedule.pk).exists())
        self.assertEqual(
            VetSchedule.objects.filter(
                staff=staff,
                branch=self.new_branch,
                date=timezone.localdate(),
                start_time=time(8),
            ).count(),
            1,
        )

    def test_staff_edit_branch_change_moves_owned_schedules(self):
        user, staff = self.create_staff(
            'admin-schedule-owner',
            'admin-schedule-owner-test-role',
            self.old_branch,
            StaffMember.Position.VETERINARIAN,
            (SpecialPermissionCodes.MANAGE_OWN_SCHEDULE,),
        )
        schedule = VetSchedule.objects.create(
            staff=staff,
            branch=self.old_branch,
            date=timezone.localdate() + timedelta(days=4),
            start_time=time(9),
            end_time=time(12),
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('employees:staff_edit', args=[user.pk]),
            {
                'branch': str(self.new_branch.pk),
                'is_active': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        schedule.refresh_from_db()
        self.assertEqual(schedule.branch_id, self.new_branch.pk)

    def _create_appointment_with_changing_vet(
        self,
        suffix,
        replacement_role=None,
        appointment_time=time(10),
    ):
        user, staff = self.create_staff(
            f'changing-vet-{suffix}',
            'veterinarian',
            self.old_branch,
            StaffMember.Position.VETERINARIAN,
            (SpecialPermissionCodes.MANAGE_OWN_SCHEDULE,),
        )
        owner = get_user_model().objects.create_user(
            username=f'pet-owner-{suffix}',
            email=f'pet-owner-{suffix}@example.com',
            password='A-secure-test-password-923!',
        )
        replacement = None
        if replacement_role:
            position = (
                StaffMember.Position.VETERINARIAN
                if replacement_role == 'veterinarian'
                else StaffMember.Position.VET_ASSISTANT
            )
            _, replacement = self.create_staff(
                f'replacement-{suffix}',
                replacement_role,
                self.old_branch,
                position,
            )

        appointment_date = timezone.localdate() + timedelta(days=8)
        if replacement:
            VetSchedule.objects.create(
                staff=replacement,
                branch=self.old_branch,
                date=appointment_date,
                start_time=time(9),
                end_time=time(12),
            )
        appointment = Appointment.objects.create(
            owner_name=owner.get_full_name() or owner.username,
            owner_email=owner.email,
            pet_name='Milo',
            branch=self.old_branch,
            preferred_vet=staff,
            appointment_date=appointment_date,
            appointment_time=appointment_time,
            status=Appointment.Status.CONFIRMED,
            user=owner,
        )
        return user, staff, owner, appointment, replacement

    def test_branch_change_reassigns_appointment_to_vet_and_notifies_owner(self):
        user, staff, owner, appointment, replacement = self._create_appointment_with_changing_vet(
            'vet-first', 'veterinarian',
        )
        self.client.force_login(user)

        with patch('employees.branch_changes.send_notification_email', return_value=True) as email_mock:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    reverse('accounts:profile'),
                    self.profile_data(user, self.new_branch),
                )

        self.assertEqual(response.status_code, 302)
        appointment.refresh_from_db()
        self.assertEqual(appointment.preferred_vet_id, replacement.pk)
        self.assertEqual(appointment.branch_id, self.old_branch.pk)
        self.assertEqual(appointment.appointment_date, timezone.localdate() + timedelta(days=8))
        notice = Notification.objects.get(user=owner, related_object_id=appointment.pk)
        self.assertEqual(notice.module_context, Notification.ModuleContext.APPOINTMENTS)
        self.assertFalse(notice.is_read)
        self.assertIn('temporarily changed branches', notice.message)
        self.assertIn(replacement.full_name, notice.message)
        email_mock.assert_called_once()
        self.assertEqual(email_mock.call_args.kwargs['recipient_list'], [owner.email])
        self.assertTrue(email_mock.call_args.kwargs['force'])
        self.assertEqual(email_mock.call_args.kwargs['from_email'], settings.DEFAULT_FROM_EMAIL)

        owner_client = Client()
        owner_client.force_login(owner)
        recent_response = owner_client.get(reverse('notifications:notification_list'))
        self.assertContains(recent_response, 'Preferred veterinarian changed for Milo')
        self.assertIn(notice, recent_response.context['recent_notifications'])
        self.assertEqual(recent_response.context['unread_notifications_count'], 1)

        appointments_response = owner_client.get(reverse('appointments:my_appointments'))
        self.assertEqual(appointments_response.status_code, 200)
        self.assertEqual(appointments_response.context['unread_notifications_count'], 0)
        notice.refresh_from_db()
        self.assertTrue(notice.is_read)

        notifications_response = owner_client.get(reverse('notifications:notification_list'))
        self.assertContains(notifications_response, 'Preferred veterinarian changed for Milo')
        self.assertContains(notifications_response, 'Appointment Rescheduled')
        self.assertIn(notice, notifications_response.context['notifications'])
        self.assertEqual(notifications_response.context['unread_notifications_count'], 0)

    def test_preferred_vet_change_always_creates_a_fresh_unread_notification(self):
        from notifications.utils import create_notification

        user, staff, owner, appointment, replacement = self._create_appointment_with_changing_vet(
            'fresh-notification', 'veterinarian',
        )
        self.client.force_login(user)

        with patch('employees.branch_changes.send_notification_email', return_value=True):
            with patch(
                'employees.branch_changes.create_notification',
                wraps=create_notification,
            ) as create_notification_mock:
                with self.captureOnCommitCallbacks(execute=True):
                    response = self.client.post(
                        reverse('accounts:profile'),
                        self.profile_data(user, self.new_branch),
                    )

        self.assertEqual(response.status_code, 302)
        create_notification_mock.assert_called_once()
        self.assertEqual(
            create_notification_mock.call_args.kwargs['dedupe_window_minutes'],
            0,
        )
        notification = Notification.objects.get(
            user=owner,
            related_object_id=appointment.pk,
            notification_type=Notification.NotificationType.APPOINTMENT_RESCHEDULED,
        )
        self.assertFalse(notification.is_read)

    def test_branch_change_falls_back_to_scheduled_vet_assistant(self):
        user, staff, owner, appointment, replacement = self._create_appointment_with_changing_vet(
            'assistant-fallback', 'assistant_veterinarian',
        )

        apply_staff_branch_change(user, self.old_branch.pk, self.new_branch)

        appointment.refresh_from_db()
        self.assertEqual(appointment.preferred_vet_id, replacement.pk)
        self.assertEqual(replacement.position, StaffMember.Position.VET_ASSISTANT)

    def test_branch_change_unassigns_vet_and_notifies_if_no_replacement_is_available(self):
        for suffix, appointment_time, period_label in (
            ('no-replacement-morning', time(9), 'Morning'),
            ('no-replacement-afternoon', time(14), 'Afternoon'),
        ):
            with self.subTest(period=period_label):
                user, staff, owner, appointment, _ = self._create_appointment_with_changing_vet(
                    suffix,
                    appointment_time=appointment_time,
                )

                with patch('employees.branch_changes.send_notification_email', return_value=True):
                    with self.captureOnCommitCallbacks(execute=True):
                        apply_staff_branch_change(user, self.old_branch.pk, self.new_branch)

                appointment.refresh_from_db()
                self.assertIsNone(appointment.preferred_vet_id)
                expected_flexible_time = time(8) if period_label == 'Morning' else time(13)
                self.assertEqual(appointment.appointment_time, expected_flexible_time)
                notice = Notification.objects.get(user=owner, related_object_id=appointment.pk)
                self.assertIn('Any Available Vet', notice.message)
                self.assertIn(f'the {period_label} flexible slot', notice.message)
                self.assertIn(
                    f'original {appointment_time.strftime("%I:%M %p")} booking has been moved',
                    notice.message,
                )