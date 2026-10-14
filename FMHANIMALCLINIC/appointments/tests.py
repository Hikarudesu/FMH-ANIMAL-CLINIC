from datetime import date, datetime, time, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from accounts.rbac_models import Module, ModulePermission, Role
from appointments.models import Appointment
from appointments.forms import AdminQuickCreateForm, AppointmentEditForm
from branches.models import Branch
from employees.models import StaffMember
from settings.models import ReasonForVisit


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
            '-- Any Available Vet --',
        )


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
    def test_appointment_can_be_marked_completed_on_scheduled_date(
        self, mocked_localdate, _mocked_double_booking,
    ):
        mocked_localdate.return_value = date(2026, 10, 14)
        form = self.completion_form(date(2026, 10, 14))

        self.assertTrue(form.is_valid(), form.errors)