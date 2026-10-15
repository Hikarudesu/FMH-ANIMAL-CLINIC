from datetime import date, datetime, time, timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.activity_context import reset_current_actor, set_current_actor
from accounts.models import User
from accounts.rbac_models import Module, ModulePermission, Role
from appointments.models import Appointment, AppointmentHistory
from appointments.forms import (
    AdminQuickCreateForm,
    AppointmentEditForm,
    PublicAppointmentForm,
    _validate_appointment_date,
)
from appointments.services import AppointmentService
from branches.models import Branch
from employees.models import StaffMember, VetSchedule
from settings.models import ReasonForVisit


class AppointmentAdvanceWindowSettingsTests(TestCase):
    def test_configured_maximum_advance_window_is_enforced(self):
        today = date(2026, 10, 15)
        with patch('appointments.forms.timezone.localdate', return_value=today):
            with patch('appointments.forms.get_setting', return_value=30):
                _validate_appointment_date(date(2026, 11, 14))

                with self.assertRaisesMessage(
                    ValidationError,
                    'Appointment date cannot be more than 30 days in advance.',
                ):
                    _validate_appointment_date(date(2026, 11, 15))


class ExpiredAppointmentCleanupTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name='Test Branch')
        self.now = timezone.make_aware(datetime(2026, 10, 5, 12, 0))

    def create_appointment(self, scheduled_at, status=Appointment.Status.PENDING):
        return Appointment.objects.create(
            owner_name='Test Owner',
            pet_name='Test Pet',
            branch=self.branch,
            appointment_date=scheduled_at.date(),
            appointment_time=scheduled_at.time(),
            status=status,
        )

    @patch('appointments.models.timezone.now')
    def test_cancels_pending_appointments_at_24_hour_deadline(self, mocked_now):
        mocked_now.return_value = self.now
        overdue = self.create_appointment(self.now - timedelta(hours=24, minutes=1))
        at_deadline = self.create_appointment(self.now - timedelta(hours=24))
        recent = self.create_appointment(self.now - timedelta(hours=23, minutes=59))
        confirmed = self.create_appointment(
            self.now - timedelta(days=3), status=Appointment.Status.CONFIRMED,
        )

        cancelled_count = Appointment.cleanup_expired()

        self.assertEqual(cancelled_count, 2)
        overdue.refresh_from_db()
        at_deadline.refresh_from_db()
        recent.refresh_from_db()
        confirmed.refresh_from_db()
        self.assertEqual(overdue.status, Appointment.Status.CANCELLED)
        self.assertEqual(at_deadline.status, Appointment.Status.CANCELLED)
        self.assertEqual(recent.status, Appointment.Status.PENDING)
        self.assertEqual(confirmed.status, Appointment.Status.CONFIRMED)
        expiry_event = AppointmentHistory.objects.get(
            appointment=overdue,
            event_type=AppointmentHistory.EventType.STATUS_CHANGED,
        )
        self.assertEqual(expiry_event.summary, 'Appointment cancelled')
        self.assertIn(
            'Automatically cancelled',
            expiry_event.changes[1]['to'],
        )

    @patch('appointments.models.timezone.now')
    def test_cleanup_preserves_cancelled_appointment_records(self, mocked_now):
        mocked_now.return_value = self.now
        appointment = self.create_appointment(self.now - timedelta(days=2))

        Appointment.cleanup_expired()

        self.assertTrue(Appointment.objects.filter(pk=appointment.pk).exists())

    @patch('appointments.models.timezone.now')
    def test_countdown_is_active_only_during_pending_24_hour_window(self, mocked_now):
        mocked_now.return_value = self.now
        started = self.create_appointment(self.now - timedelta(minutes=1))
        future = self.create_appointment(self.now + timedelta(minutes=1))
        expired = self.create_appointment(self.now - timedelta(hours=24, minutes=1))
        confirmed = self.create_appointment(
            self.now - timedelta(minutes=1), status=Appointment.Status.CONFIRMED,
        )

        self.assertTrue(started.auto_cancel_countdown_active)
        self.assertFalse(future.auto_cancel_countdown_active)
        self.assertFalse(expired.auto_cancel_countdown_active)
        self.assertFalse(confirmed.auto_cancel_countdown_active)


class ScheduledAppointmentCleanupTests(TestCase):
    @patch('appointments.management.commands.run_scheduled_tasks.call_command')
    @patch('appointments.management.commands.run_scheduled_tasks.cache.delete')
    @patch(
        'appointments.management.commands.run_scheduled_tasks.cache.add',
        return_value=True,
    )
    @patch(
        'appointments.services.AppointmentService.cleanup_expired_appointments',
        return_value=2,
    )
    def test_scheduled_task_runner_executes_appointment_cleanup(
        self, cleanup, _cache_add, _cache_delete, _call_command,
    ):
        output = StringIO()

        call_command('run_scheduled_tasks', stdout=output)

        cleanup.assert_called_once_with()
        self.assertIn('Cancelled 2 expired pending appointment(s).', output.getvalue())


class AppointmentScheduleLockTests(TransactionTestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name='Schedule Lock Branch')
        role, _ = Role.objects.get_or_create(
            code='veterinarian',
            defaults={
                'name': 'Veterinarian',
                'hierarchy_level': 3,
                'is_staff_role': True,
            },
        )
        user = User.objects.create_user(
            username='schedule-lock-vet',
            email='schedule-lock-vet@example.com',
            password='A-secure-test-password-923!',
            assigned_role=role,
        )
        staff = StaffMember.objects.create(
            user=user,
            first_name='Schedule',
            last_name='Lock Vet',
            position=StaffMember.Position.VETERINARIAN,
            branch=self.branch,
        )
        self.appointment_date = timezone.localdate() + timedelta(days=3)
        self.schedule = VetSchedule.objects.create(
            staff=staff,
            branch=self.branch,
            date=self.appointment_date,
            start_time=time(9),
            end_time=time(12),
        )

    def test_booking_lock_locks_scheduled_staff_rows_for_branch_and_date(self):
        with CaptureQueriesContext(connection) as captured_queries:
            with transaction.atomic():
                AppointmentService.lock_booking_schedule(
                    self.branch.pk,
                    self.appointment_date.isoformat(),
                )

        lock_queries = [
            query['sql'] for query in captured_queries
            if 'FOR UPDATE OF "employees_vetschedule"' in query['sql']
        ]
        self.assertEqual(len(lock_queries), 1)

    def test_booking_lock_requires_an_open_transaction(self):
        with self.assertRaises(RuntimeError):
            AppointmentService.lock_booking_schedule(
                self.branch.pk,
                self.appointment_date.isoformat(),
            )


class AppointmentTimeDisplayTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name='Appointment Time Display Branch')
        role, _ = Role.objects.get_or_create(
            code='veterinarian',
            defaults={
                'name': 'Veterinarian',
                'hierarchy_level': 3,
                'is_staff_role': True,
            },
        )
        vet_user = User.objects.create_user(
            username='time-display-vet',
            email='time-display-vet@example.com',
            password='A-secure-test-password-923!',
            assigned_role=role,
        )
        self.vet = StaffMember.objects.create(
            user=vet_user,
            first_name='Time',
            last_name='Display Vet',
            position=StaffMember.Position.VETERINARIAN,
            branch=self.branch,
        )

    def create_appointment(self, appointment_time, preferred_vet=None):
        return Appointment(
            owner_name='Test Owner',
            pet_name='Test Pet',
            branch=self.branch,
            appointment_date=timezone.localdate(),
            appointment_time=appointment_time,
            preferred_vet=preferred_vet,
        )

    def test_preferred_vet_appointment_displays_exact_flexible_hour(self):
        morning = self.create_appointment(time(8), self.vet)
        afternoon = self.create_appointment(time(13), self.vet)

        self.assertEqual(morning.appointment_time_display, '08:00 AM')
        self.assertEqual(afternoon.appointment_time_display, '01:00 PM')

    def test_any_available_appointment_keeps_flexible_period_label(self):
        morning = self.create_appointment(time(8))
        afternoon = self.create_appointment(time(13))

        self.assertEqual(morning.appointment_time_display, 'Morning')
        self.assertEqual(afternoon.appointment_time_display, 'Afternoon')


@override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }
)
class ViewOnlyAppointmentScopeTests(TestCase):
    def setUp(self):
        self.old_branch = Branch.objects.create(name='Former Vet Branch')
        self.current_branch = Branch.objects.create(name='Current Vet Branch')
        self.role = Role.objects.create(
            name='Appointments View Only',
            code='appointments-view-only-test',
            hierarchy_level=2,
            is_staff_role=True,
        )
        appointments_module, _ = Module.objects.get_or_create(
            code='appointments',
            defaults={'name': 'Appointments'},
        )
        ModulePermission.objects.create(
            role=self.role,
            module=appointments_module,
            permission_type=ModulePermission.PermissionType.VIEW,
        )
        self.vet_user = User.objects.create_user(
            username='view-only-former-vet',
            email='view-only-former-vet@example.com',
            password='A-secure-test-password-923!',
            assigned_role=self.role,
            branch=self.current_branch,
        )
        self.vet = StaffMember.objects.create(
            user=self.vet_user,
            first_name='Former',
            last_name='Vet',
            position=StaffMember.Position.VETERINARIAN,
            branch=self.current_branch,
        )
        self.own_appointment = Appointment.objects.create(
            owner_name='Assigned Owner',
            pet_name='Assigned Pet',
            branch=self.old_branch,
            preferred_vet=self.vet,
            appointment_date=timezone.localdate() + timedelta(days=3),
            appointment_time=time(9),
        )
        self.other_appointment = Appointment.objects.create(
            owner_name='Other Owner',
            pet_name='Other Pet',
            branch=self.current_branch,
            appointment_date=timezone.localdate() + timedelta(days=3),
            appointment_time=time(10),
        )
        self.client.force_login(self.vet_user)

    def test_view_only_role_sees_only_assigned_appointments_in_list_and_calendar(self):
        list_response = self.client.get(reverse('appointments:admin_list'))
        calendar_response = self.client.get(
            reverse('appointments:admin_calendar_api'),
            {
                'year': (timezone.localdate() + timedelta(days=3)).year,
                'month': (timezone.localdate() + timedelta(days=3)).month,
            },
        )

        self.assertEqual(list_response.status_code, 200)
        visible_list = list(list_response.context['appointments'].object_list)
        self.assertEqual([appointment.pk for appointment in visible_list], [self.own_appointment.pk])
        own_detail_response = self.client.get(
            reverse('appointments:admin_detail', args=[self.own_appointment.pk])
        )
        other_detail_response = self.client.get(
            reverse('appointments:admin_detail', args=[self.other_appointment.pk])
        )
        self.assertEqual(own_detail_response.status_code, 200)
        self.assertEqual(other_detail_response.status_code, 404)
        self.assertEqual(calendar_response.status_code, 200)
        visible_calendar_ids = [event['id'] for event in calendar_response.json()['events']]
        self.assertEqual(visible_calendar_ids, [self.own_appointment.pk])


class InactiveStaffAppointmentOptionsTests(TestCase):
    def test_inactive_veterinarian_is_not_available_for_quick_appointment(self):
        branch = Branch.objects.create(name='Inactive Vet Test Branch')
        role, _ = Role.objects.get_or_create(
            code='veterinarian',
            defaults={
                'name': 'Veterinarian',
                'hierarchy_level': 3,
                'is_staff_role': True,
            },
        )
        user = User.objects.create_user(
            username='inactive-vet-option',
            email='inactive-vet-option@example.com',
            password='A-secure-test-password-923!',
            assigned_role=role,
            is_active=False,
        )
        staff = StaffMember.objects.create(
            user=user,
            first_name='Inactive',
            last_name='Veterinarian',
            position=StaffMember.Position.VETERINARIAN,
            branch=branch,
            is_active=False,
        )

        form = AdminQuickCreateForm(data={'branch': str(branch.pk)})

        self.assertFalse(
            form.fields['preferred_vet'].queryset.filter(pk=staff.pk).exists()
        )


class AdminQuickCreateOwnerValidationTests(TestCase):
    def test_walkin_owner_name_is_required(self):
        form = AdminQuickCreateForm(data={'source': Appointment.Source.WALKIN})

        self.assertFalse(form.is_valid())
        self.assertIn('owner_name', form.errors)
        self.assertEqual(
            form.errors['owner_name'][0],
            'Owner name is required for walk-in appointments.',
        )


class FlexibleAppointmentTimeTests(TestCase):
    def test_morning_booking_uses_first_available_time_not_fixed_eight_am(self):
        branch = Branch.objects.create(name='Flexible Booking Branch')
        vet_role, _ = Role.objects.get_or_create(
            code='veterinarian',
            defaults={
                'name': 'Veterinarian',
                'hierarchy_level': 3,
                'is_staff_role': True,
            },
        )
        vet_user = User.objects.create_user(
            username='flexible-booking-vet',
            email='flexible-booking-vet@example.com',
            password='A-secure-test-password-923!',
            assigned_role=vet_role,
            branch=branch,
        )
        vet = StaffMember.objects.create(
            user=vet_user,
            first_name='Flexible',
            last_name='Booking Vet',
            position=StaffMember.Position.VETERINARIAN,
            branch=branch,
        )
        appointment_date = timezone.localdate() + timedelta(days=1)
        VetSchedule.objects.create(
            staff=vet,
            date=appointment_date,
            start_time=time(8),
            end_time=time(12),
            branch=branch,
        )
        Appointment.objects.create(
            owner_name='Earlier Owner',
            pet_name='Earlier Pet',
            branch=branch,
            preferred_vet=vet,
            appointment_date=appointment_date,
            appointment_time=time(8),
            status=Appointment.Status.CONFIRMED,
        )
        other_branch = Branch.objects.create(name='Other Flexible Booking Branch')
        Appointment.objects.create(
            owner_name='Other Branch Owner',
            pet_name='Other Branch Pet',
            branch=other_branch,
            preferred_vet=vet,
            appointment_date=appointment_date,
            appointment_time=time(8, 30),
            status=Appointment.Status.CONFIRMED,
        )
        reason = ReasonForVisit.objects.create(
            name='General Consultation',
            code='FLEXIBLE_BOOKING_GENERAL',
        )

        form = PublicAppointmentForm(data={
            'owner_name': 'New Owner',
            'pet_name': 'New Pet',
            'pet_species': 'Dog',
            'pet_sex': 'MALE',
            'branch': str(branch.pk),
            'appointment_date': appointment_date.isoformat(),
            'appointment_time': 'MORNING',
            'reason': str(reason.pk),
        })

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['appointment_time'], time(8, 30))


class AdminQuickCreateOwnerApiTests(TestCase):
    def test_owner_name_field_is_not_required_for_portal_form_rendering(self):
        form = AdminQuickCreateForm()

        self.assertFalse(form.fields['owner_name'].required)

    def test_owner_api_includes_registered_accounts_without_pets(self):
        admin = User.objects.create_superuser(
            username='quick-create-owner-api-admin',
            email='quick-create-owner-api-admin@example.com',
            password='A-secure-test-password-923!',
        )
        new_owner = User.objects.create_user(
            username='new-appointment-owner',
            email='new-appointment-owner@example.com',
            password='A-secure-test-password-923!',
            first_name='New',
            last_name='Owner',
        )
        self.client.force_login(admin)

        response = self.client.get(reverse('appointments:api_owners'))

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            new_owner.pk,
            [owner['id'] for owner in response.json()['owners']],
        )


class AppointmentEditVeterinarianOptionalTests(TestCase):
    def test_veterinarian_is_optional_when_editing_appointment(self):
        form = AppointmentEditForm()

        self.assertFalse(form.fields['preferred_vet'].required)
        self.assertEqual(
            form.fields['preferred_vet'].empty_label,
            '-- No preference (unassigned until consultation) --',
        )


@override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }
)
class OwnerAppointmentCancellationTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name='Owner Cancellation Branch')
        self.owner = User.objects.create_user(
            username='owner-cancellation',
            email='owner-cancellation@example.com',
            password='A-secure-test-password-923!',
        )
        self.appointment = Appointment.objects.create(
            owner_name='Appointment Owner',
            owner_email=self.owner.email,
            pet_name='Cancellation Pet',
            branch=self.branch,
            user=self.owner,
            appointment_date=timezone.localdate() + timedelta(days=3),
            appointment_time=time(10),
        )
        self.client.force_login(self.owner)
        self.cancel_url = reverse(
            'appointments:portal_cancel',
            args=[self.appointment.pk],
        )

    @patch('appointments.views.notify_staff_appointment_status_change')
    @patch('appointments.views.notify_appointment_status_change')
    def test_owner_cancels_pending_appointment_and_staff_are_notified(
        self, notify_owner, notify_staff,
    ):
        response = self.client.post(
            self.cancel_url,
            {'cancellation_reason': 'Schedule changed.'},
        )

        self.assertRedirects(
            response,
            reverse('appointments:my_appointments'),
            fetch_redirect_response=False,
        )
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.CANCELLED)
        self.assertEqual(
            self.appointment.cancellation_reason,
            'Schedule changed.',
        )
        notify_owner.assert_called_once()
        notify_staff.assert_called_once()
        self.assertEqual(notify_staff.call_args.args[0], self.appointment)

    @patch('appointments.views.notify_staff_appointment_status_change')
    @patch('appointments.views.notify_appointment_status_change')
    def test_owner_can_cancel_a_confirmed_appointment(
        self, _notify_owner, _notify_staff,
    ):
        self.appointment.status = Appointment.Status.CONFIRMED
        self.appointment.save(update_fields=['status', 'updated_at'])

        self.client.post(
            self.cancel_url,
            {'cancellation_reason': 'Plans have changed.'},
        )

        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.CANCELLED)
        self.assertEqual(
            self.appointment.cancellation_reason,
            'Plans have changed.',
        )

    def test_owner_cannot_cancel_within_24_hours_of_appointment(self):
        appointment_time = timezone.localtime(
            timezone.now() + timedelta(hours=23),
        )
        self.appointment.appointment_date = appointment_time.date()
        self.appointment.appointment_time = appointment_time.time()
        self.appointment.save(
            update_fields=['appointment_date', 'appointment_time', 'updated_at'],
        )

        response = self.client.post(
            self.cancel_url,
            {'cancellation_reason': 'Schedule changed.'},
        )

        self.assertRedirects(
            response,
            reverse('appointments:my_appointments'),
            fetch_redirect_response=False,
        )
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.PENDING)

    @patch('appointments.models.timezone.now')
    def test_owner_can_cancel_at_exact_24_hour_cutoff(self, mocked_now):
        mocked_now.return_value = (
            self.appointment.scheduled_datetime - timedelta(hours=24)
        )
        self.assertTrue(self.appointment.owner_can_cancel)

    def test_owner_cancellation_requires_reason_and_appointment_ownership(self):
        self.client.post(self.cancel_url, {'cancellation_reason': '   '})
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.PENDING)

        another_owner = User.objects.create_user(
            username='another-appointment-owner',
            email='another-appointment-owner@example.com',
            password='A-secure-test-password-923!',
        )
        self.client.force_login(another_owner)
        response = self.client.post(
            self.cancel_url,
            {'cancellation_reason': 'Schedule changed.'},
        )

        self.assertEqual(response.status_code, 404)

    def test_owner_portal_shows_cancel_form_before_cutoff(self):
        response = self.client.get(reverse('appointments:my_appointments'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cancel this appointment')
        self.assertContains(response, 'Appointment History')
        self.assertContains(response, 'Cancellation is available until 24 hours before your appointment.')

    def test_portal_history_shows_only_owner_visible_entries_for_own_appointments(self):
        owner_visible = AppointmentHistory.objects.create(
            appointment=self.appointment,
            event_type=AppointmentHistory.EventType.UPDATED,
            summary='Appointment schedule updated',
            changes=[{'field': 'Date', 'from': '2026-11-01', 'to': '2026-11-02'}],
            owner_visible=True,
        )
        AppointmentHistory.objects.create(
            appointment=self.appointment,
            event_type=AppointmentHistory.EventType.UPDATED,
            summary='Private staff note',
            changes=[{'field': 'Medical record decision', 'from': 'Pending', 'to': 'Required'}],
            owner_visible=False,
        )
        another_owner = User.objects.create_user(
            username='another-history-owner',
            email='another-history-owner@example.com',
            password='A-secure-test-password-923!',
        )
        other_appointment = Appointment.objects.create(
            owner_name='Another Owner',
            pet_name='Private Pet',
            branch=self.branch,
            user=another_owner,
            appointment_date=timezone.localdate() + timedelta(days=4),
            appointment_time=time(11),
        )
        AppointmentHistory.objects.create(
            appointment=other_appointment,
            event_type=AppointmentHistory.EventType.UPDATED,
            summary='Another owner private update',
            owner_visible=True,
        )

        response = self.client.get(reverse('appointments:my_appointment_history'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, owner_visible.summary)
        self.assertNotContains(response, 'Private staff note')
        self.assertNotContains(response, 'Another owner private update')
        detail_response = self.client.get(reverse(
            'appointments:my_appointment_history_detail',
            args=[owner_visible.pk],
        ))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(response, owner_visible.summary)
        self.assertContains(detail_response, '2026-11-01')
        self.assertNotContains(detail_response, 'Medical record decision')
        self.assertNotContains(detail_response, 'Required')

    def test_appointment_history_is_retained_when_appointment_is_deleted(self):
        history = AppointmentHistory.objects.get(
            appointment=self.appointment,
            event_type=AppointmentHistory.EventType.BOOKED,
        )

        self.appointment.delete()

        history.refresh_from_db()
        self.assertIsNone(history.appointment_id)

    def test_appointment_changes_record_actor_and_before_after_values(self):
        token = set_current_actor(self.owner)
        try:
            appointment = Appointment.objects.create(
                owner_name='Audit Owner',
                pet_name='Audit Pet',
                branch=self.branch,
                user=self.owner,
                appointment_date=timezone.localdate() + timedelta(days=5),
                appointment_time=time(12),
            )
            appointment.status = Appointment.Status.CONFIRMED
            appointment.save(update_fields=['status', 'updated_at'])
        finally:
            reset_current_actor(token)

        booking = AppointmentHistory.objects.get(
            appointment=appointment,
            event_type=AppointmentHistory.EventType.BOOKED,
        )
        status_change = AppointmentHistory.objects.get(
            appointment=appointment,
            event_type=AppointmentHistory.EventType.STATUS_CHANGED,
        )
        self.assertEqual(booking.actor, self.owner)
        self.assertEqual(status_change.actor, self.owner)
        self.assertEqual(status_change.changes[0]['from'], 'Pending')
        self.assertEqual(status_change.changes[0]['to'], 'Confirmed')


class AppointmentStaffHistoryVisibilityTests(TestCase):
    @override_settings(
        STORAGES={
            'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
            'staticfiles': {
                'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
            },
        }
    )
    def test_only_requested_staff_roles_see_the_detailed_history(self):
        branch = Branch.objects.create(name='History Branch')
        module, _ = Module.objects.get_or_create(
            code='appointments',
            defaults={'name': 'Appointments'},
        )
        role = Role.objects.create(
            name='History Receptionist',
            code='cashier',
            hierarchy_level=2,
            is_staff_role=True,
        )
        for permission_type in (
            ModulePermission.PermissionType.VIEW,
            ModulePermission.PermissionType.EDIT,
        ):
            ModulePermission.objects.create(
                role=role,
                module=module,
                permission_type=permission_type,
            )
        user = User.objects.create_user(
            username='history-receptionist',
            email='history-receptionist@example.com',
            password='A-secure-test-password-923!',
            assigned_role=role,
            branch=branch,
        )
        appointment = Appointment.objects.create(
            owner_name='History Owner',
            pet_name='History Pet',
            branch=branch,
            appointment_date=timezone.localdate(),
            appointment_time=time(10),
        )
        AppointmentHistory.objects.create(
            appointment=appointment,
            event_type=AppointmentHistory.EventType.UPDATED,
            summary='Appointment schedule updated',
            changes=[{'field': 'Date', 'from': '2026-10-20', 'to': '2026-10-21'}],
            owner_visible=True,
        )
        self.client.force_login(user)
        history_url = reverse('appointments:admin_appointment_history')
        appointments_response = self.client.get(
            reverse('appointments:admin_list'),
        )
        self.assertEqual(appointments_response.status_code, 200)
        self.assertContains(appointments_response, 'Appointment History')

        staff_response = self.client.get(history_url)

        self.assertEqual(staff_response.status_code, 200)
        self.assertContains(staff_response, 'Appointment History')
        history = AppointmentHistory.objects.get(
            appointment=appointment,
            summary='Appointment schedule updated',
        )
        detail_response = self.client.get(reverse(
            'appointments:admin_appointment_history_detail',
            args=[history.pk],
        ))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, 'Changes in this event')
        self.assertContains(detail_response, 'Date')
        self.assertContains(detail_response, '2026-10-20')

        role.code = 'other_staff'
        role.save(update_fields=['code'])
        other_role_response = self.client.get(history_url)

        self.assertEqual(other_role_response.status_code, 403)


class AppointmentCompletionDateValidationTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name='Completion Date Branch')
        self.reason = ReasonForVisit.objects.create(
            name='General Consultation',
            code='COMPLETION_TEST',
        )
        self.appointment = Appointment.objects.create(
            owner_name='Test Owner',
            owner_email='owner@example.com',
            owner_phone='09123456789',
            pet_name='Test Pet',
            pet_species='Dog',
            pet_sex='MALE',
            branch=self.branch,
            appointment_date=date(2026, 10, 14),
            appointment_time=time(9),
            reason_for_visit=self.reason,
            status=Appointment.Status.CONFIRMED,
        )

    def completion_form(self, appointment_date):
        return AppointmentEditForm(
            data={
                'owner_name': self.appointment.owner_name,
                'owner_email': self.appointment.owner_email,
                'owner_phone': self.appointment.owner_phone,
                'owner_address': '',
                'pet_name': self.appointment.pet_name,
                'pet_species': self.appointment.pet_species,
                'pet_breed': '',
                'pet_dob': '',
                'pet_sex': self.appointment.pet_sex,
                'pet_color': '',
                'pet_symptoms': '',
                'branch': self.branch.pk,
                'preferred_vet': '',
                'appointment_date': appointment_date.isoformat(),
                'appointment_time': '09:00',
                'reason': self.reason.pk,
                'status': Appointment.Status.COMPLETED,
                'source': Appointment.Source.WALKIN,
                'notes': '',
            },
            instance=self.appointment,
        )

    @patch('appointments.forms._check_double_booking')
    @patch('appointments.forms.timezone.localdate')
    def test_future_appointment_cannot_be_marked_completed(
        self, mocked_localdate, _mocked_double_booking,
    ):
        mocked_localdate.return_value = date(2026, 10, 13)
        form = self.completion_form(date(2026, 10, 14))

        self.assertFalse(form.is_valid())
        self.assertIn(
            'This appointment cannot be marked completed before its scheduled date.',
            form.errors['status'],
        )

    @patch('appointments.forms._check_double_booking')
    @patch('appointments.forms.timezone.localdate')
    def test_status_cannot_be_changed_through_generic_edit_form(
        self, mocked_localdate, _mocked_double_booking,
    ):
        mocked_localdate.return_value = date(2026, 10, 14)
        form = self.completion_form(date(2026, 10, 14))

        self.assertFalse(form.is_valid())
        self.assertIn(
            'Use the appointment workflow actions to change appointment status.',
            form.errors['status'],
        )


@override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }
)
class AppointmentWorkflowActionTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name='Workflow Test Branch')
        self.role = Role.objects.create(
            name='Workflow Receptionist',
            code='workflow-receptionist-test',
            hierarchy_level=2,
            is_staff_role=True,
        )
        module, _ = Module.objects.get_or_create(
            code='appointments',
            defaults={'name': 'Appointments'},
        )
        ModulePermission.objects.create(
            role=self.role,
            module=module,
            permission_type=ModulePermission.PermissionType.EDIT,
        )
        ModulePermission.objects.create(
            role=self.role,
            module=module,
            permission_type=ModulePermission.PermissionType.VIEW,
        )
        self.user = User.objects.create_user(
            username='workflow-receptionist',
            email='workflow-receptionist@example.com',
            password='A-secure-test-password-923!',
            assigned_role=self.role,
            branch=self.branch,
        )
        self.appointment = Appointment.objects.create(
            owner_name='Workflow Owner',
            pet_name='Workflow Pet',
            branch=self.branch,
            appointment_date=timezone.localdate(),
            appointment_time=time(10),
        )
        self.client.force_login(self.user)

    def test_receptionist_manages_appointment_in_dedicated_workspace(self):
        list_response = self.client.get(reverse('appointments:admin_list'))

        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, 'Manage appointment')
        self.assertContains(list_response, 'Pending')
        self.assertContains(list_response, 'Walk-In / Guest User')
        self.assertNotContains(list_response, 'class="admin-badge')
        self.assertNotContains(list_response, 'Cancellation reason')
        self.assertNotContains(list_response, 'Confirm appointment')

        detail_response = self.client.get(
            reverse('appointments:admin_detail', args=[self.appointment.pk])
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, self.appointment.owner_name)
        self.assertContains(detail_response, self.appointment.pet_name)
        self.assertContains(detail_response, 'Confirm appointment')
        self.assertContains(detail_response, 'Cancellation reason')

    def test_completed_appointment_list_hides_record_status_indicators(self):
        self.appointment.status = Appointment.Status.COMPLETED
        self.appointment.save(update_fields=['status', 'updated_at'])

        response = self.client.get(reverse('appointments:admin_list'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Medical Record Pending')
        self.assertNotContains(response, 'Medical Record Added')
        self.assertNotContains(response, 'Record saved')
        self.assertNotContains(response, 'View Medical Records')

    def test_cancellation_requires_and_saves_reason(self):
        url = reverse(
            'appointments:admin_workflow_action',
            args=[self.appointment.pk, 'cancel'],
        )

        response = self.client.post(url, {'cancellation_reason': '  '})
        self.assertEqual(response.status_code, 302)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.PENDING)

        response = self.client.post(
            url, {'cancellation_reason': 'Owner requested cancellation.'},
        )
        self.assertEqual(response.status_code, 302)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.CANCELLED)
        self.assertEqual(
            self.appointment.cancellation_reason,
            'Owner requested cancellation.',
        )

    def test_receptionist_confirms_then_checks_in(self):
        confirm_url = reverse(
            'appointments:admin_workflow_action',
            args=[self.appointment.pk, 'confirm'],
        )
        check_in_url = reverse(
            'appointments:admin_workflow_action',
            args=[self.appointment.pk, 'check-in'],
        )

        response = self.client.post(confirm_url)
        self.assertRedirects(
            response,
            reverse('appointments:admin_detail', args=[self.appointment.pk]),
            fetch_redirect_response=False,
        )
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.CONFIRMED)

        self.assertEqual(self.client.post(check_in_url).status_code, 302)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.CHECKED_IN)
        self.assertIsNotNone(self.appointment.checked_in_at)

    def test_future_appointment_can_be_confirmed_but_not_checked_in(self):
        self.appointment.appointment_date = timezone.localdate() + timedelta(days=1)
        self.appointment.save(update_fields=['appointment_date', 'updated_at'])
        confirm_url = reverse(
            'appointments:admin_workflow_action',
            args=[self.appointment.pk, 'confirm'],
        )
        check_in_url = reverse(
            'appointments:admin_workflow_action',
            args=[self.appointment.pk, 'check-in'],
        )

        self.assertEqual(self.client.post(confirm_url).status_code, 302)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.CONFIRMED)

        list_response = self.client.get(reverse('appointments:admin_list'))
        self.assertEqual(list_response.status_code, 200)
        detail_response = self.client.get(
            reverse('appointments:admin_detail', args=[self.appointment.pk])
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, 'Check-in and consultation can begin on the scheduled date.')
        self.assertContains(
            list_response,
            'Check-in and consultation are available on the scheduled date.',
        )
        self.assertNotContains(detail_response, '> Check in</button>')

        self.assertEqual(self.client.post(check_in_url).status_code, 302)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.CONFIRMED)
        self.assertIsNone(self.appointment.checked_in_at)

    def test_veterinarian_manages_branch_and_unassigned_visits_in_appointments(self):
        vet_role, _ = Role.objects.get_or_create(
            code='veterinarian',
            defaults={
                'name': 'Veterinarian',
                'hierarchy_level': 3,
                'is_staff_role': True,
            },
        )
        module = Module.objects.get(code='appointments')
        ModulePermission.objects.get_or_create(
            role=vet_role,
            module=module,
            permission_type=ModulePermission.PermissionType.VIEW,
        )
        vet_user = User.objects.create_user(
            username='appointments-module-vet',
            email='appointments-module-vet@example.com',
            password='A-secure-test-password-923!',
            assigned_role=vet_role,
            branch=self.branch,
        )
        vet = StaffMember.objects.create(
            user=vet_user,
            first_name='Appointments',
            last_name='Vet',
            position=StaffMember.Position.VETERINARIAN,
            branch=self.branch,
        )
        self.appointment.status = Appointment.Status.CONFIRMED
        self.appointment.preferred_vet = vet
        self.appointment.save(update_fields=['status', 'preferred_vet', 'updated_at'])
        unassigned_appointment = Appointment.objects.create(
            owner_name='Unassigned Owner',
            pet_name='Unassigned Pet',
            branch=self.branch,
            appointment_date=timezone.localdate(),
            appointment_time=time(11),
            status=Appointment.Status.CONFIRMED,
        )
        other_branch = Branch.objects.create(name='Other Workflow Branch')
        Appointment.objects.create(
            owner_name='Other Branch Owner',
            pet_name='Other Branch Pet',
            branch=other_branch,
            appointment_date=timezone.localdate(),
            appointment_time=time(12),
            status=Appointment.Status.CONFIRMED,
        )
        self.client.force_login(vet_user)

        response = self.client.get(reverse('appointments:admin_list'))

        self.assertEqual(response.status_code, 200)
        listed_appointments = list(response.context['appointments'])
        self.assertEqual(
            {appointment.pk for appointment in listed_appointments},
            {self.appointment.pk, unassigned_appointment.pk},
        )
        self.assertContains(response, 'Open consultation')
        self.assertNotContains(response, 'Veterinary visit actions')
        self.assertNotContains(response, 'Other Branch Pet')

        detail_response = self.client.get(
            reverse('appointments:admin_detail', args=[self.appointment.pk])
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, 'Veterinary consultation')
        self.assertContains(detail_response, 'Start consultation')
        self.assertNotContains(detail_response, 'Confirm appointment')

        calendar_response = self.client.get(
            reverse('appointments:admin_calendar_api'),
            {
                'year': timezone.localdate().year,
                'month': timezone.localdate().month,
            },
        )
        self.assertEqual(calendar_response.status_code, 200)
        self.assertEqual(
            {event['id'] for event in calendar_response.json()['events']},
            {self.appointment.pk, unassigned_appointment.pk},
        )
        for event in calendar_response.json()['events']:
            self.assertNotIn('latestRecordId', event)
            self.assertNotIn('hasMedicalRecords', event)

    def test_confirmed_appointment_marks_check_in_as_optional(self):
        self.appointment.status = Appointment.Status.CONFIRMED
        self.appointment.save(update_fields=['status', 'updated_at'])

        steps = self.appointment.workflow_progress

        self.assertEqual(steps[1]['state'], 'done')
        self.assertEqual(steps[2]['state'], 'optional')
        self.assertTrue(steps[2]['optional'])
        self.assertEqual(steps[3]['state'], 'upcoming')

    def test_veterinarian_must_explain_no_record_decision(self):
        vet_role, _ = Role.objects.get_or_create(
            code='veterinarian',
            defaults={
                'name': 'Veterinarian',
                'hierarchy_level': 3,
                'is_staff_role': True,
            },
        )
        module = Module.objects.get(code='appointments')
        ModulePermission.objects.get_or_create(
            role=vet_role,
            module=module,
            permission_type=ModulePermission.PermissionType.VIEW,
        )
        vet_user = User.objects.create_user(
            username='workflow-vet',
            email='workflow-vet@example.com',
            password='A-secure-test-password-923!',
            assigned_role=vet_role,
            branch=self.branch,
        )
        vet = StaffMember.objects.create(
            user=vet_user,
            first_name='Workflow',
            last_name='Vet',
            position=StaffMember.Position.VETERINARIAN,
            branch=self.branch,
        )
        self.appointment.status = Appointment.Status.CONFIRMED
        self.appointment.preferred_vet = vet
        self.appointment.appointment_date = timezone.localdate() + timedelta(days=1)
        self.appointment.checked_in_at = None
        self.appointment.save()
        self.client.force_login(vet_user)

        start_url = reverse(
            'appointments:vet_workflow_action',
            args=[self.appointment.pk, 'start'],
        )
        no_record_url = reverse(
            'appointments:vet_workflow_action',
            args=[self.appointment.pk, 'no-record'],
        )
        future_detail_response = self.client.get(
            reverse('appointments:admin_detail', args=[self.appointment.pk])
        )
        self.assertEqual(future_detail_response.status_code, 200)
        self.assertContains(future_detail_response, 'Check-in and consultation can begin on the scheduled date.')
        self.assertNotContains(future_detail_response, 'Start consultation')

        self.assertEqual(self.client.post(start_url).status_code, 302)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.CONFIRMED)

        self.appointment.appointment_date = timezone.localdate()
        self.appointment.save(update_fields=['appointment_date', 'updated_at'])
        self.assertEqual(self.client.post(start_url).status_code, 302)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.IN_PROGRESS)
        self.assertIsNone(self.appointment.checked_in_at)
        self.assertEqual(self.appointment.preferred_vet_id, vet.pk)

        self.client.post(no_record_url, {'medical_record_decision_reason': '  '})
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.IN_PROGRESS)

        self.client.post(
            no_record_url,
            {'medical_record_decision_reason': 'Routine check, no treatment required.'},
        )
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.AWAITING_PAYMENT)
        self.assertEqual(
            self.appointment.medical_record_decision,
            Appointment.MedicalRecordDecision.NOT_REQUIRED,
        )