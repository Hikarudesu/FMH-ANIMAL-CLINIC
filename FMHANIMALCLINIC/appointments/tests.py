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
    _check_double_booking,
    _validate_appointment_date,
)
from appointments.services import AppointmentService
from branches.models import Branch
from employees.models import StaffMember, VetSchedule
from notifications.models import FollowUp, Notification
from patients.models import Pet
from pos.models import Payment, Sale, SaleItem
from records.models import MedicalRecord, RecordEntry
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
        followup = FollowUp.objects.create(
            appointment=confirmed,
            booked_appointment=overdue,
            pet_name=overdue.pet_name,
            follow_up_date=overdue.appointment_date,
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
        followup.refresh_from_db()
        self.assertTrue(followup.is_expired)
        self.assertIn('automatically cancelled', followup.expiration_reason)
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
        command_names = [call.args[0] for call in _call_command.call_args_list]
        self.assertLess(
            command_names.index('expire_followups'),
            command_names.index('send_followup_emails'),
        )
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


class SameDayBookingCutoffTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name='Same Day Booking Branch')
        role, _ = Role.objects.get_or_create(
            code='veterinarian',
            defaults={
                'name': 'Veterinarian',
                'hierarchy_level': 3,
                'is_staff_role': True,
            },
        )
        user = User.objects.create_user(
            username='same-day-booking-vet',
            email='same-day-booking-vet@example.com',
            password='A-secure-test-password-923!',
            assigned_role=role,
            branch=self.branch,
        )
        self.vet = StaffMember.objects.create(
            user=user,
            first_name='Same Day',
            last_name='Booking Vet',
            position=StaffMember.Position.VETERINARIAN,
            branch=self.branch,
        )
        self.appointment_date = date(2026, 10, 17)
        self.now = timezone.make_aware(
            datetime.combine(self.appointment_date, time(10, 43)),
            timezone.get_current_timezone(),
        )
        VetSchedule.objects.create(
            staff=self.vet,
            branch=self.branch,
            date=self.appointment_date,
            start_time=time(10),
            end_time=time(12),
        )

    def test_availability_clamps_legacy_schedules_to_clinic_hours(self):
        target_date = timezone.localdate() + timedelta(days=1)
        VetSchedule.objects.create(
            staff=self.vet,
            branch=self.branch,
            date=target_date,
            start_time=time(7),
            end_time=time(20),
        )

        slots = AppointmentService.get_available_slots(
            target_date=target_date,
            branch_id=self.branch.pk,
        )
        slot_times = {slot['time'] for slot in slots}

        self.assertIn('08:00', slot_times)
        self.assertIn('18:30', slot_times)
        self.assertNotIn('07:30', slot_times)
        self.assertNotIn('19:00', slot_times)
        self.assertTrue(AppointmentService.check_slot_availability(
            branch_id=self.branch.pk,
            appointment_date=target_date,
            appointment_time=time(18, 30),
            vet_id=self.vet.pk,
        ))
        self.assertFalse(AppointmentService.check_slot_availability(
            branch_id=self.branch.pk,
            appointment_date=target_date,
            appointment_time=time(18, 45),
            vet_id=self.vet.pk,
        ))

    def test_submission_rejects_slots_that_end_after_clinic_closing(self):
        with self.assertRaisesMessage(
            ValidationError,
            'Appointments must be scheduled between 8:00 AM and 7:00 PM.',
        ):
            _check_double_booking({
                'branch': self.branch,
                'preferred_vet': self.vet,
                'appointment_date': timezone.localdate() + timedelta(days=1),
                'appointment_time': time(18, 45),
            })

    @patch('appointments.services.timezone.localtime')
    def test_availability_marks_elapsed_slots_unavailable(self, mocked_localtime):
        mocked_localtime.return_value = self.now

        slots = AppointmentService.get_available_slots(
            target_date=self.appointment_date,
            branch_id=self.branch.pk,
        )

        slots_by_time = {slot['time']: slot for slot in slots}
        self.assertFalse(slots_by_time['10:00']['available'])
        self.assertEqual(slots_by_time['10:00']['booked_label'], 'Time has passed')
        self.assertFalse(slots_by_time['10:30']['available'])
        self.assertEqual(slots_by_time['10:30']['booked_label'], 'Time has passed')
        self.assertTrue(slots_by_time['11:00']['available'])
        self.assertTrue(slots_by_time['11:30']['available'])

        edit_slots = AppointmentService.get_available_slots(
            target_date=self.appointment_date,
            branch_id=self.branch.pk,
            include_elapsed_slots=True,
        )
        self.assertTrue(edit_slots[0]['available'])

    @patch('appointments.forms.AppointmentService.get_available_slots')
    @patch('appointments.forms.timezone.localtime')
    @patch('appointments.forms.timezone.localdate')
    def test_submission_rejects_elapsed_slot_but_accepts_future_slot(
        self, mocked_localdate, mocked_localtime, mocked_slots,
    ):
        mocked_localdate.return_value = self.appointment_date
        mocked_localtime.return_value = self.now
        cleaned_data = {
            'branch': self.branch,
            'preferred_vet': self.vet,
            'appointment_date': self.appointment_date,
            'appointment_time': time(10, 30),
        }

        with self.assertRaisesMessage(
            ValidationError,
            'This appointment time has already passed. Please select a future time slot.',
        ):
            _check_double_booking(cleaned_data)
        mocked_slots.assert_not_called()

        cleaned_data['appointment_time'] = time(11)
        mocked_slots.return_value = [{'time': '11:00', 'available': True}]
        _check_double_booking(cleaned_data)
        mocked_slots.assert_called_once()


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
class AppointmentEditFollowUpTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name='Appointment Edit Follow-up Branch')
        self.owner = User.objects.create_user(
            username='appointment-edit-followup-owner',
            email='appointment-edit-followup@example.com',
        )
        self.pet = Pet.objects.create(
            owner=self.owner,
            source=Pet.Source.PORTAL,
            name='Appointment Edit Follow-up Pet',
            species='Dog',
            sex=Pet.Sex.FEMALE,
        )
        self.appointment = Appointment.objects.create(
            owner_name='Appointment Edit Follow-up Owner',
            owner_email=self.owner.email,
            pet_name=self.pet.name,
            pet=self.pet,
            user=self.owner,
            branch=self.branch,
            appointment_date=timezone.localdate() + timedelta(days=3),
            appointment_time=time(10),
        )
        self.followup = FollowUp.objects.create(
            appointment=self.appointment,
            pet_name=self.pet.name,
            follow_up_date=timezone.localdate() + timedelta(days=10),
            reason='Medication recheck',
        )
        self.admin = User.objects.create_superuser(
            username='appointment-edit-followup-admin',
            email='appointment-edit-followup-admin@example.com',
            password='A-secure-test-password-923!',
        )
        self.client.force_login(self.admin)

    def test_unchecking_recommendation_removes_it_when_appointment_is_saved(self):
        edit_url = reverse(
            'appointments:admin_edit',
            args=[self.appointment.pk],
        )

        get_response = self.client.get(edit_url)

        self.assertEqual(get_response.status_code, 200)
        self.assertContains(get_response, 'follow_up_enabled')
        self.assertContains(get_response, 'Medication recheck')

        with patch('appointments.views.AppointmentEditForm') as form_class:
            form = form_class.return_value
            form.is_valid.return_value = True
            form.save.return_value = self.appointment
            response = self.client.post(edit_url, {})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(FollowUp.objects.filter(pk=self.followup.pk).exists())


@override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }
)
class FollowUpAppointmentBookingTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name='Follow-up Booking Branch')
        self.owner = User.objects.create_user(
            username='follow-up-booking-owner',
            email='follow-up-booking@example.com',
            password='A-secure-test-password-923!',
            phone_number='09123456789',
        )
        self.pet = Pet.objects.create(
            owner=self.owner,
            source=Pet.Source.PORTAL,
            name='Follow-up Pet',
            species='Dog',
            sex=Pet.Sex.FEMALE,
        )
        reason = ReasonForVisit.objects.create(
            name='Follow-up Examination',
            code='FOLLOW_UP_BOOKING_EXAM',
        )
        today = timezone.localdate()
        self.source_appointment = Appointment.objects.create(
            owner_name='Follow-up Owner',
            owner_email=self.owner.email,
            owner_phone=self.owner.phone_number,
            pet_name=self.pet.name,
            pet=self.pet,
            user=self.owner,
            branch=self.branch,
            reason_for_visit=reason,
            appointment_date=today,
            appointment_time=time(10),
            status=Appointment.Status.COMPLETED,
        )
        self.followup = FollowUp.objects.create(
            appointment=self.source_appointment,
            pet_name=self.pet.name,
            follow_up_date=today + timedelta(days=7),
            reason='Post-treatment recheck',
        )
        vet_role, _ = Role.objects.get_or_create(
            code='veterinarian',
            defaults={
                'name': 'Veterinarian',
                'hierarchy_level': 3,
                'is_staff_role': True,
            },
        )
        vet_user = User.objects.create_user(
            username='follow-up-booking-vet',
            email='follow-up-booking-vet@example.com',
            assigned_role=vet_role,
            branch=self.branch,
        )
        self.vet = StaffMember.objects.create(
            user=vet_user,
            first_name='Follow-up',
            last_name='Veterinarian',
            position=StaffMember.Position.VETERINARIAN,
            branch=self.branch,
        )
        self.source_appointment.preferred_vet = self.vet
        self.source_appointment.save(update_fields=['preferred_vet'])
        self.booking_date = today + timedelta(days=7)
        VetSchedule.objects.create(
            staff=self.vet,
            branch=self.branch,
            date=self.booking_date,
            start_time=time(9),
            end_time=time(12),
        )
        self.client.force_login(self.owner)

    @patch('appointments.views.notify_staff_appointment_status_change')
    @patch('appointments.views.send_appointment_confirmation')
    def test_owner_books_follow_up_as_a_separate_appointment(
        self, send_confirmation, _notify_staff,
    ):
        response = self.client.post(
            reverse('appointments:portal_book'),
            {
                'follow_up_id': self.followup.pk,
                'selected_pet_id': self.pet.pk,
                'owner_name': 'Follow-up Owner',
                'owner_email': self.owner.email,
                'owner_phone': self.owner.phone_number,
                'owner_address': '',
                'pet_name': self.pet.name,
                'pet_species': self.pet.species,
                'pet_breed': '',
                'pet_dob': '',
                'pet_sex': self.pet.sex,
                'pet_color': '',
                'pet_symptoms': 'Post-treatment recheck',
                'branch': self.branch.pk,
                'appointment_date': self.booking_date.isoformat(),
                'appointment_time': '09:00',
                'preferred_vet': '',
                'reason': self.source_appointment.reason_for_visit_id,
                'notes': '',
            },
        )

        self.assertRedirects(
            response,
            reverse('appointments:my_appointments'),
            fetch_redirect_response=False,
        )
        self.followup.refresh_from_db()
        booked_appointment = self.followup.booked_appointment
        self.assertIsNotNone(booked_appointment)
        self.assertNotEqual(booked_appointment.pk, self.source_appointment.pk)
        self.assertEqual(booked_appointment.user_id, self.owner.pk)
        self.assertEqual(booked_appointment.pet_id, self.pet.pk)
        self.assertEqual(
            booked_appointment.appointment_date,
            self.booking_date,
        )
        self.assertIn(
            'Follow-up visit for the recommendation dated',
            booked_appointment.notes,
        )
        self.assertIn(self.followup.reason, booked_appointment.notes)
        self.assertFalse(self.followup.is_completed)
        send_confirmation.assert_called_once_with(booked_appointment)

    def test_owner_cannot_open_another_owners_follow_up_booking(self):
        another_owner = User.objects.create_user(
            username='different-follow-up-owner',
            email='different-follow-up-owner@example.com',
            password='A-secure-test-password-923!',
        )
        self.client.force_login(another_owner)

        response = self.client.get(
            reverse('appointments:portal_book'),
            {'follow_up': self.followup.pk},
        )

        self.assertEqual(response.status_code, 404)

    def test_recommended_follow_up_appears_in_owner_portal_for_booking(self):
        response = self.client.get(
            reverse('appointments:my_appointments'),
            {'tab': 'followups'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.followup.reason)
        self.assertContains(response, 'Book return visit')

    def test_appointment_follow_up_prefills_branch_date_and_scheduled_vet(self):
        response = self.client.get(
            reverse('appointments:portal_book'),
            {'follow_up': self.followup.pk},
        )

        self.assertEqual(response.status_code, 200)
        booking_form = response.context['form']
        self.assertEqual(booking_form['branch'].value(), self.branch.pk)
        self.assertEqual(
            booking_form['appointment_date'].value(),
            self.booking_date,
        )
        self.assertEqual(
            booking_form['preferred_vet'].value(),
            self.vet.pk,
        )
        self.assertIn(
            self.vet,
            booking_form.fields['preferred_vet'].queryset,
        )
        self.assertFalse(booking_form['appointment_time'].value())

    def test_follow_up_creator_remains_prefilled_when_not_scheduled(self):
        self.source_appointment.preferred_vet = None
        self.source_appointment.save(update_fields=['preferred_vet'])
        self.followup.created_by = self.vet.user
        self.followup.save(update_fields=['created_by'])
        VetSchedule.objects.filter(
            staff=self.vet,
            date=self.booking_date,
        ).delete()

        response = self.client.get(
            reverse('appointments:portal_book'),
            {'follow_up': self.followup.pk},
        )

        self.assertEqual(response.status_code, 200)
        booking_form = response.context['form']
        self.assertEqual(booking_form['preferred_vet'].value(), self.vet.pk)
        self.assertIn(
            self.vet,
            booking_form.fields['preferred_vet'].queryset,
        )
        self.assertEqual(
            booking_form.fields['preferred_vet'].widget.attrs[
                'data-followup-prefill-vet'
            ],
            str(self.vet.pk),
        )
        self.assertEqual(
            booking_form.fields['preferred_vet'].widget.attrs[
                'data-followup-prefill-branch'
            ],
            str(self.branch.pk),
        )

    def test_medical_record_only_follow_up_is_visible_and_prefills_pet(self):
        record = MedicalRecord.objects.create(
            pet=self.pet,
            branch=self.branch,
            vet=self.vet,
            date_recorded=timezone.localdate(),
        )
        followup_date = timezone.localdate() + timedelta(days=9)
        VetSchedule.objects.create(
            staff=self.vet,
            branch=self.branch,
            date=followup_date,
            start_time=time(9),
            end_time=time(12),
        )
        followup = FollowUp.objects.create(
            medical_record=record,
            pet_name=self.pet.name,
            follow_up_date=followup_date,
            reason='Follow-up from a medical record',
        )

        response = self.client.get(
            reverse('appointments:portal_book'),
            {'follow_up': followup.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context['selected_pet_id'],
            self.pet.pk,
        )
        self.assertContains(response, 'Booking a return visit')
        self.assertEqual(
            response.context['form']['branch'].value(),
            self.branch.pk,
        )
        self.assertEqual(
            response.context['form']['appointment_date'].value(),
            followup_date,
        )
        self.assertEqual(
            response.context['form']['preferred_vet'].value(),
            self.vet.pk,
        )
        self.assertFalse(
            response.context['form']['appointment_time'].value(),
        )

    def test_staff_follow_up_link_opens_prefilled_booking_modal(self):
        staff = User.objects.create_superuser(
            username='follow-up-booking-admin',
            email='follow-up-booking-admin@example.com',
            password='A-secure-test-password-923!',
        )
        self.client.force_login(staff)

        response = self.client.get(
            reverse('appointments:admin_list'),
            {'follow_up': self.followup.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['followup_booking'].pk, self.followup.pk)
        self.assertContains(response, 'Book Return Visit')
        self.assertContains(response, 'followupBookingData')

    def test_quick_create_does_not_offer_follow_up_recommendation(self):
        staff = User.objects.create_superuser(
            username='quick-create-follow-up-admin',
            email='quick-create-follow-up-admin@example.com',
            password='A-secure-test-password-923!',
        )
        self.client.force_login(staff)

        response = self.client.get(reverse('appointments:admin_list'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'quickFollowUpEnabled')
        self.assertNotContains(response, 'quickFollowUpFields')

    @patch('appointments.views.notify_staff_appointment_status_change')
    @patch('appointments.views.notify_appointment_status_change')
    def test_completing_booked_return_visit_completes_recommendation(
        self, _notify_owner, _notify_staff,
    ):
        staff = User.objects.create_superuser(
            username='follow-up-completion-admin',
            email='follow-up-completion-admin@example.com',
            password='A-secure-test-password-923!',
        )
        booked_appointment = Appointment.objects.create(
            owner_name='Follow-up Owner',
            owner_email=self.owner.email,
            pet_name=self.pet.name,
            pet=self.pet,
            user=self.owner,
            branch=self.branch,
            appointment_date=timezone.localdate(),
            appointment_time=time(10),
            status=Appointment.Status.AWAITING_PAYMENT,
            medical_record_decision=Appointment.MedicalRecordDecision.NOT_REQUIRED,
        )
        sale = Sale.objects.create(
            branch=self.branch,
            subtotal=100,
            total=100,
            amount_paid=100,
            status=Sale.Status.COMPLETED,
        )
        booked_appointment.sale = sale
        booked_appointment.save(update_fields=['sale', 'updated_at'])
        self.followup.booked_appointment = booked_appointment
        self.followup.save(update_fields=['booked_appointment'])
        self.client.force_login(staff)

        response = self.client.post(
            reverse(
                'appointments:admin_workflow_action',
                args=[booked_appointment.pk, 'complete'],
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.followup.refresh_from_db()
        booked_appointment.refresh_from_db()
        self.assertEqual(booked_appointment.status, Appointment.Status.COMPLETED)
        self.assertTrue(self.followup.is_completed)


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

    def test_owner_can_cancel_within_24_hours_of_appointment(self):
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
        self.assertEqual(self.appointment.status, Appointment.Status.CANCELLED)

    @patch('appointments.views.notify_staff_appointment_status_change')
    @patch('appointments.views.notify_appointment_status_change')
    def test_cancelling_booked_follow_up_removes_recommendation(
        self, _notify_owner, _notify_staff,
    ):
        source_appointment = Appointment.objects.create(
            owner_name='Appointment Owner',
            owner_email=self.owner.email,
            pet_name='Cancellation Pet',
            branch=self.branch,
            user=self.owner,
            appointment_date=timezone.localdate() - timedelta(days=2),
            appointment_time=time(10),
            status=Appointment.Status.COMPLETED,
        )
        followup = FollowUp.objects.create(
            appointment=source_appointment,
            booked_appointment=self.appointment,
            pet_name=self.appointment.pet_name,
            follow_up_date=self.appointment.appointment_date,
        )

        response = self.client.post(
            self.cancel_url,
            {'cancellation_reason': 'Schedule changed.'},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(FollowUp.objects.filter(pk=followup.pk).exists())
        self.assertTrue(Appointment.objects.filter(pk=self.appointment.pk).exists())

    def test_owner_can_cancel_after_appointment_time_if_not_checked_in(self):
        self.appointment.appointment_date = timezone.localdate() - timedelta(days=1)
        self.appointment.save(update_fields=['appointment_date', 'updated_at'])
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

    def test_owner_portal_shows_cancellation_form_without_time_cutoff(self):
        response = self.client.get(reverse('appointments:my_appointments'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'View details')
        self.assertContains(response, reverse(
            'appointments:portal_detail',
            args=[self.appointment.pk],
        ))
        self.assertNotContains(response, 'appt-card-collapse')
        self.assertContains(response, 'Appointment History')
        detail_response = self.client.get(reverse(
            'appointments:portal_detail',
            args=[self.appointment.pk],
        ))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, 'Cancel appointment')
        self.assertContains(detail_response, 'You can cancel until clinic staff check in your pet.')
        self.assertContains(detail_response, 'Your information')
        self.assertContains(detail_response, 'Pet information')
        self.assertContains(detail_response, 'Visit details')

    @patch('notifications.email_utils.send_notification_email', return_value=True)
    def test_owner_cancellation_sends_customer_email(self, send_email):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.cancel_url,
                {'cancellation_reason': 'Emergency appointment cancellation.'},
            )

        self.assertEqual(response.status_code, 302)
        send_email.assert_called_once()
        self.assertEqual(
            send_email.call_args.kwargs['recipient_list'],
            [self.owner.email],
        )
        self.assertIn('Emergency appointment cancellation.', send_email.call_args.kwargs['message'])

    def test_each_portal_appointment_tab_paginates_after_ten_entries(self):
        appointments_by_status = {}
        for status, tab_name in (
            (Appointment.Status.PENDING, 'pending'),
            (Appointment.Status.CONFIRMED, 'confirmed'),
            (Appointment.Status.COMPLETED, 'completed'),
            (Appointment.Status.CANCELLED, 'cancelled'),
        ):
            additional_count = 10 if tab_name == 'pending' else 11
            Appointment.objects.bulk_create([
                Appointment(
                    owner_name=self.owner.get_full_name() or self.owner.username,
                    owner_email=self.owner.email,
                    pet_name=f'{tab_name.title()} Pet {index}',
                    branch=self.branch,
                    user=self.owner,
                    appointment_date=timezone.localdate() + timedelta(days=index + 5),
                    appointment_time=time(10),
                    status=status,
                )
                for index in range(additional_count)
            ])
            appointments_by_status[tab_name] = list(
                Appointment.objects.filter(
                    user=self.owner,
                    status=status,
                ).order_by('-appointment_date', '-appointment_time')
            )

        followup_appointments = appointments_by_status['pending'][:]
        FollowUp.objects.bulk_create([
            FollowUp(
                appointment=appointment,
                pet_name=appointment.pet_name,
                follow_up_date=timezone.localdate() + timedelta(days=index + 10),
            )
            for index, appointment in enumerate(followup_appointments)
        ])

        tab_configs = (
            ('pending', 'pending_appts'),
            ('confirmed', 'confirmed_appts'),
            ('completed', 'completed_appts'),
            ('cancelled', 'cancelled_appts'),
            ('followups', 'follow_ups'),
        )
        for tab_name, context_name in tab_configs:
            with self.subTest(tab=tab_name):
                response = self.client.get(
                    reverse('appointments:my_appointments'),
                    {
                        'tab': tab_name,
                        f'{tab_name}_page': 2,
                    },
                )

                page_obj = response.context[context_name]
                self.assertEqual(response.status_code, 200)
                self.assertEqual(page_obj.paginator.count, 11)
                self.assertEqual(len(page_obj.object_list), 1)
                self.assertEqual(page_obj.number, 2)
                self.assertEqual(response.context['active_tab'], tab_name)
                self.assertContains(
                    response,
                    f'class="appt-tab-content active" id="tab-{tab_name}"',
                )

    def test_portal_appointment_detail_requires_ownership(self):
        another_owner = User.objects.create_user(
            username='appointment-detail-other-owner',
            email='appointment-detail-other-owner@example.com',
            password='A-secure-test-password-923!',
        )
        self.client.force_login(another_owner)

        response = self.client.get(reverse(
            'appointments:portal_detail',
            args=[self.appointment.pk],
        ))

        self.assertEqual(response.status_code, 404)

    def test_portal_appointment_details_include_owned_payment_and_medical_information(self):
        self.appointment.status = Appointment.Status.CANCELLED
        self.appointment.cancellation_reason = 'Owner had a schedule conflict.'
        self.appointment.medical_record_decision = (
            Appointment.MedicalRecordDecision.NOT_REQUIRED
        )
        self.appointment.medical_record_decision_reason = (
            'No additional record was needed for this visit.'
        )
        self.appointment.save(update_fields=[
            'status',
            'cancellation_reason',
            'medical_record_decision',
            'medical_record_decision_reason',
            'updated_at',
        ])
        sale = Sale.objects.create(
            branch=self.branch,
            subtotal=500,
            total=500,
            amount_paid=200,
        )
        self.appointment.sale = sale
        self.appointment.save(update_fields=['sale', 'updated_at'])
        SaleItem.objects.create(
            sale=sale,
            item_type=SaleItem.ItemType.SERVICE,
            name='Consultation',
            unit_price=500,
        )
        Payment.objects.create(
            sale=sale,
            method=Payment.Method.CASH,
            amount=200,
        )
        pet = Pet.objects.create(
            owner=self.owner,
            name='Cancellation Pet',
            species='Dog',
            sex=Pet.Sex.FEMALE,
        )
        record = MedicalRecord.objects.create(
            pet=pet,
            branch=self.branch,
            date_recorded=timezone.localdate(),
        )
        RecordEntry.objects.create(
            record=record,
            appointment=self.appointment,
            date_recorded=timezone.localdate(),
            history_clinical_signs='Mild coughing reported.',
            treatment='Rest and hydration.',
            rx='Cough syrup as directed.',
        )

        response = self.client.get(reverse(
            'appointments:portal_detail',
            args=[self.appointment.pk],
        ))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'POS summary')
        self.assertContains(response, 'Consultation')
        self.assertContains(response, 'Balance due')
        self.assertContains(response, 'Medical record for this visit')
        self.assertContains(response, 'Mild coughing reported.')
        self.assertContains(response, 'Rest and hydration.')
        self.assertContains(response, 'Cough syrup as directed.')
        self.assertContains(response, "Veterinarian's reason")
        self.assertContains(response, 'No additional record was needed for this visit.')
        self.assertContains(response, 'Owner had a schedule conflict.')

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
        self.assertContains(detail_response, 'Your information')
        self.assertContains(detail_response, 'Pet information')
        self.assertContains(detail_response, 'Clinic location')
        self.assertContains(detail_response, 'Visit details')
        self.assertContains(detail_response, 'current information')
        self.assertNotContains(detail_response, 'Medical record decision')
        self.assertNotContains(detail_response, 'Required')

        filtered_response = self.client.get(
            reverse('appointments:my_appointment_history'),
            {'status': Appointment.Status.CANCELLED},
        )
        self.assertEqual(filtered_response.status_code, 200)
        self.assertNotContains(filtered_response, owner_visible.summary)
        self.assertContains(filtered_response, 'All Status')
        self.assertContains(filtered_response, 'Cancelled')

        pending_response = self.client.get(
            reverse('appointments:my_appointment_history'),
            {'status': Appointment.Status.PENDING},
        )
        self.assertEqual(pending_response.status_code, 200)
        self.assertContains(pending_response, owner_visible.summary)
        for _, label in Appointment.Status.choices:
            self.assertContains(pending_response, label)

    def test_portal_history_search_suggestions_are_owner_scoped(self):
        AppointmentHistory.objects.create(
            appointment=self.appointment,
            event_type=AppointmentHistory.EventType.UPDATED,
            summary='Owner visible update',
            owner_visible=True,
        )
        other_owner = User.objects.create_user(
            username='suggestion-owner',
            email='suggestion-owner@example.com',
            password='A-secure-test-password-923!',
        )
        other_appointment = Appointment.objects.create(
            owner_name='Suggestion Owner',
            pet_name='Private Suggestion Pet',
            branch=self.branch,
            user=other_owner,
            appointment_date=timezone.localdate() + timedelta(days=4),
            appointment_time=time(11),
        )
        AppointmentHistory.objects.create(
            appointment=other_appointment,
            event_type=AppointmentHistory.EventType.BOOKED,
            summary='Private suggestion',
            owner_visible=True,
        )

        response = self.client.get(
            reverse('appointments:my_appointment_history_search'),
            {'q': 'Pet', 'status': Appointment.Status.CANCELLED},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'], [])

        pending_response = self.client.get(
            reverse('appointments:my_appointment_history_search'),
            {'q': 'Pet', 'status': Appointment.Status.PENDING},
        )
        self.assertEqual(
            [result['value'] for result in pending_response.json()['results']],
            ['Cancellation Pet'],
        )

    def test_portal_history_search_matches_owner_pet_status_and_visit_details(self):
        visible_entry = AppointmentHistory.objects.create(
            appointment=self.appointment,
            event_type=AppointmentHistory.EventType.UPDATED,
            summary='Appointment details updated',
            owner_visible=True,
        )
        history_url = reverse('appointments:my_appointment_history')
        for query in (
            'Cancellation Pet',
            'Appointment Owner',
            'Pending',
            'Owner Cancellation Branch',
        ):
            with self.subTest(query=query):
                response = self.client.get(history_url, {'q': query})

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, visible_entry.summary)

        response = self.client.get(history_url, {'q': 'Cancellation Pet'})
        self.assertContains(response, 'Appointment · Pending')
        self.assertContains(response, 'Cancellation Pet')
        self.assertContains(response, 'View details')
        self.assertContains(response, 'name="q"')

        no_match_response = self.client.get(
            history_url,
            {'q': 'No such pet'},
        )
        self.assertEqual(no_match_response.status_code, 200)
        self.assertContains(no_match_response, 'No matching appointment history')
        self.assertNotContains(no_match_response, visible_entry.summary)

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
        self.assertNotContains(appointments_response, 'Appointment History')

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
        self.assertContains(detail_response, 'What changed')
        self.assertContains(detail_response, 'Date')
        self.assertContains(detail_response, '2026-10-20')
        self.assertContains(detail_response, 'Current appointment details')
        self.assertContains(detail_response, 'Reason for visit')

        veterinarian_role, _ = Role.objects.get_or_create(
            code='veterinarian',
            defaults={
                'name': 'Veterinarian',
                'hierarchy_level': 3,
                'is_staff_role': True,
            },
        )
        ModulePermission.objects.get_or_create(
            role=veterinarian_role,
            module=module,
            permission_type=ModulePermission.PermissionType.VIEW,
        )
        user.assigned_role = veterinarian_role
        user.save(update_fields=['assigned_role'])
        veterinarian_response = self.client.get(reverse('appointments:admin_list'))
        self.assertEqual(veterinarian_response.status_code, 200)
        self.assertNotContains(veterinarian_response, 'Appointment History')

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
        ModulePermission.objects.create(
            role=self.role,
            module=module,
            permission_type=ModulePermission.PermissionType.DELETE,
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

    def test_appointment_statuses_render_as_colored_bubbles(self):
        for status in Appointment.Status.values:
            if status != self.appointment.status:
                Appointment.objects.create(
                    owner_name=f'{status} Owner',
                    pet_name=f'{status} Pet',
                    branch=self.branch,
                    appointment_date=timezone.localdate(),
                    appointment_time=time(11),
                    status=status,
                )

        response = self.client.get(reverse('appointments:admin_list'))

        self.assertEqual(response.status_code, 200)
        for status in Appointment.Status.values:
            self.assertContains(
                response,
                f'appointment-status-bubble appointment-status--{status.lower()}',
            )

    def test_starting_consultation_notifies_only_the_assigned_veterinarian(self):
        vet_role, _ = Role.objects.get_or_create(
            code='veterinarian',
            defaults={
                'name': 'Veterinarian',
                'hierarchy_level': 3,
                'is_staff_role': True,
            },
        )
        ModulePermission.objects.get_or_create(
            role=vet_role,
            module=Module.objects.get(code='appointments'),
            permission_type=ModulePermission.PermissionType.VIEW,
        )
        veterinarian = User.objects.create_user(
            username='consultation-start-vet',
            email='consultation-start-vet@example.com',
            password='A-secure-test-password-923!',
            assigned_role=vet_role,
            branch=self.branch,
        )
        veterinarian_profile = StaffMember.objects.create(
            user=veterinarian,
            first_name='Consultation',
            last_name='Veterinarian',
            position=StaffMember.Position.VETERINARIAN,
            branch=self.branch,
        )
        owner = User.objects.create_user(
            username='consultation-start-owner',
            email='consultation-start-owner@example.com',
            password='A-secure-test-password-923!',
        )
        self.appointment.user = owner
        self.appointment.status = Appointment.Status.CONFIRMED
        self.appointment.preferred_vet = veterinarian_profile
        self.appointment.save(update_fields=[
            'user', 'status', 'preferred_vet', 'updated_at',
        ])
        Notification.objects.filter(related_object_id=self.appointment.pk).delete()
        self.client.force_login(veterinarian)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse(
                'appointments:vet_workflow_action',
                args=[self.appointment.pk, 'start'],
            ))

        self.assertEqual(response.status_code, 302)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.IN_PROGRESS)
        notifications = Notification.objects.filter(
            related_object_id=self.appointment.pk,
            notification_type=Notification.NotificationType.APPOINTMENT,
            module_context=Notification.ModuleContext.APPOINTMENTS,
        )
        self.assertEqual(notifications.count(), 1)
        self.assertEqual(notifications.get().user_id, veterinarian.pk)

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
        self.assertNotContains(detail_response, 'Delete appointment')

    @patch('notifications.email_utils.send_appointment_deletion_email', return_value=True)
    def test_staff_can_delete_cancelled_appointment_after_customer_notification(
        self, send_deletion_email,
    ):
        owner = User.objects.create_user(
            username='deleted-appointment-owner',
            email='deleted-appointment-owner@example.com',
            password='A-secure-test-password-923!',
        )
        self.appointment.user = owner
        self.appointment.owner_email = owner.email
        self.appointment.status = Appointment.Status.CANCELLED
        self.appointment.cancellation_reason = 'Emergency cancellation.'
        self.appointment.save(update_fields=[
            'user', 'owner_email', 'status', 'cancellation_reason', 'updated_at',
        ])

        detail_response = self.client.get(
            reverse('appointments:admin_detail', args=[self.appointment.pk]),
        )
        self.assertContains(detail_response, 'Delete appointment')
        self.assertContains(detail_response, 'id="appointmentDeleteDialog"')
        self.assertContains(detail_response, 'Delete cancelled appointment?')
        self.assertContains(detail_response, 'email and an in-app notification')
        self.assertContains(detail_response, 'Keep appointment')
        self.assertContains(detail_response, 'Delete permanently')
        self.assertNotContains(detail_response, 'onsubmit="return confirm(')

        delete_url = reverse(
            'appointments:admin_delete',
            args=[self.appointment.pk],
        )
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(delete_url, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.redirect_chain,
            [(reverse('appointments:admin_list'), 302)],
        )
        send_deletion_email.assert_called_once()
        self.assertFalse(Appointment.objects.filter(pk=self.appointment.pk).exists())
        self.assertTrue(Notification.objects.filter(
            user=owner,
            notification_type=Notification.NotificationType.APPOINTMENT_CANCELLED,
            title__icontains='record removed',
        ).exists())

        repeated_response = self.client.post(delete_url, follow=True)
        self.assertEqual(repeated_response.status_code, 200)
        self.assertEqual(
            repeated_response.redirect_chain,
            [(reverse('appointments:admin_list'), 302)],
        )
        self.assertContains(
            repeated_response,
            'This appointment has already been deleted.',
        )
        send_deletion_email.assert_called_once()

    @patch('notifications.email_utils.send_appointment_deletion_email')
    def test_staff_cannot_delete_non_cancelled_appointment(self, send_deletion_email):
        response = self.client.post(
            reverse('appointments:admin_delete', args=[self.appointment.pk]),
        )

        self.assertRedirects(
            response,
            reverse('appointments:admin_list'),
            fetch_redirect_response=False,
        )
        self.assertTrue(Appointment.objects.filter(pk=self.appointment.pk).exists())
        send_deletion_email.assert_not_called()

    @patch('notifications.email_utils.send_appointment_deletion_email', return_value=False)
    def test_staff_deletion_is_blocked_when_customer_email_fails(
        self, send_deletion_email,
    ):
        owner = User.objects.create_user(
            username='failed-delete-notice-owner',
            email='failed-delete-notice-owner@example.com',
            password='A-secure-test-password-923!',
        )
        self.appointment.user = owner
        self.appointment.status = Appointment.Status.CANCELLED
        self.appointment.save(update_fields=['user', 'status', 'updated_at'])

        response = self.client.post(
            reverse('appointments:admin_delete', args=[self.appointment.pk]),
        )

        self.assertRedirects(
            response,
            reverse('appointments:admin_list'),
            fetch_redirect_response=False,
        )
        self.assertTrue(Appointment.objects.filter(pk=self.appointment.pk).exists())
        send_deletion_email.assert_called_once()

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

    @patch('appointments.views.notify_staff_appointment_status_change')
    @patch('appointments.views.notify_appointment_status_change')
    @patch(
        'notifications.followup_email_service.send_notification_email',
        return_value=True,
    )
    def test_veterinarian_can_recommend_follow_up_without_medical_record(
        self, send_email, _notify_owner, _notify_staff,
    ):
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
        self.appointment.owner_email = 'guest-followup@example.com'
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

        visit_progress = self.client.get(
            reverse('appointments:admin_detail', args=[self.appointment.pk]),
        )
        self.assertContains(visit_progress, 'noRecordFollowUpEnabled')
        self.assertContains(visit_progress, 'noRecordFollowUpDate')
        self.assertContains(visit_progress, 'not a booked appointment')
        page_html = visit_progress.content.decode()
        followup_option_position = page_html.index(
            'Optional follow-up recommendation',
        )
        decision_buttons_start = page_html.index(
            'class="appointment-manage__toolbar appointment-manage__decision-buttons"',
        )
        decision_buttons = page_html[decision_buttons_start:]
        no_record_button_position = decision_buttons.index(
            '>No record needed</button>',
        )
        record_required_button_position = decision_buttons.index(
            '>Record required</button>',
        )
        self.assertLess(followup_option_position, decision_buttons_start)
        self.assertNotEqual(no_record_button_position, record_required_button_position)
        self.assertIn(
            'form="noRecordDecisionForm"',
            decision_buttons,
        )

        self.client.post(no_record_url, {'medical_record_decision_reason': '  '})
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.IN_PROGRESS)

        follow_up_date = timezone.localdate() + timedelta(days=7)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                no_record_url,
                {
                    'medical_record_decision_reason': (
                        'Routine check, no treatment required.'
                    ),
                    'follow_up_enabled': 'on',
                    'follow_up_date': follow_up_date.isoformat(),
                    'follow_up_reason': 'Medication recheck',
                },
            )
        self.assertEqual(response.status_code, 302)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.AWAITING_PAYMENT)
        self.assertEqual(
            self.appointment.medical_record_decision,
            Appointment.MedicalRecordDecision.NOT_REQUIRED,
        )
        followup = FollowUp.objects.get(appointment=self.appointment)
        self.assertIsNone(followup.medical_record_id)
        self.assertEqual(followup.follow_up_date, follow_up_date)
        self.assertEqual(followup.reason, 'Medication recheck')
        self.assertIsNone(followup.booked_appointment_id)
        send_email.assert_called_once()
        self.assertEqual(
            send_email.call_args.kwargs['recipient_list'],
            ['guest-followup@example.com'],
        )
        self.assertIn(
            'not a confirmed appointment',
            send_email.call_args.kwargs['message'],
        )