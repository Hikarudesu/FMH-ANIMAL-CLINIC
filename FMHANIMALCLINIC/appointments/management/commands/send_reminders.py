"""
Management command to send appointment reminders for the next day.
Usage: python manage.py send_reminders
"""
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from appointments.models import Appointment
from notifications.email_utils import send_appointment_reminder


class Command(BaseCommand):
    help = 'Sends email reminders for appointments scheduled for tomorrow.'

    def handle(self, *args, **kwargs):
        tomorrow = date.today() + timedelta(days=1)

        # Get confirmed appointments for tomorrow
        appointments = Appointment.objects.filter(
            appointment_date=tomorrow,
            status=Appointment.Status.CONFIRMED
        ).exclude(owner_email='')

        count = 0
        self.stdout.write(self.style.NOTICE(
            f'Found {appointments.count()} appointments for {tomorrow}.'))

        for appt in appointments:
            if send_appointment_reminder(appt):
                count += 1
                self.stdout.write(self.style.SUCCESS(
                    f'Sent reminder to {appt.owner_email} (Appt #{appt.id})'))
            else:
                self.stdout.write(self.style.ERROR(
                    f'Failed to send reminder to {appt.owner_email} (Appt #{appt.id})'))

        self.stdout.write(self.style.SUCCESS(
            f'Successfully sent {count} reminder emails.'))
