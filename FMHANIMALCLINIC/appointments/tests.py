from datetime import datetime, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from appointments.models import Appointment
from branches.models import Branch


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