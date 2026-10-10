from datetime import datetime, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from accounts.rbac_models import Role
from appointments.models import Appointment
from appointments.forms import AdminQuickCreateForm, AppointmentEditForm
from branches.models import Branch
from employees.models import StaffMember


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


class InactiveStaffAppointmentOptionsTests(TestCase):
    def test_inactive_veterinarian_is_not_available_for_quick_appointment(self):
        branch = Branch.objects.create(name='Inactive Vet Test Branch')
        role, _ = Role.objects.get_or_create(
            code='veterinarian',
            defaults={
                'name': 'Veterinarian',
                'hierarchy_level': 5,
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


class AppointmentEditVeterinarianOptionalTests(TestCase):
    def test_veterinarian_is_optional_when_editing_appointment(self):
        form = AppointmentEditForm()

        self.assertFalse(form.fields['preferred_vet'].required)
        self.assertEqual(
            form.fields['preferred_vet'].empty_label,
            '-- Any Available Vet --',
        )