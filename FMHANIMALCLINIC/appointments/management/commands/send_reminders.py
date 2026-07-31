"""
Management command to send appointment reminders.
Sends reminders at configurable intervals (default: 1 day + 3 hours before).
Usage: python manage.py send_reminders
"""
from datetime import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from appointments.models import Appointment
from notifications.models import Notification
from notifications.email_utils import send_appointment_reminder
from notifications.utils import create_notification, notify_role_users
from settings.utils import get_setting


class Command(BaseCommand):
    help = 'Sends email reminders for confirmed appointments at configured intervals.'

    def handle(self, *args, **kwargs):
        # Get reminder intervals from settings (in hours)
        reminder_1_hours = get_setting('appointment_reminder_hours_1', 24)
        reminder_2_hours = get_setting('appointment_reminder_hours_2', 3)

        now = timezone.now()
        reminders_sent = 0

        # Get confirmed appointments
        confirmed_appts = Appointment.objects.filter(
            status=Appointment.Status.CONFIRMED
        ).exclude(owner_email='').select_related('user', 'branch')

        for appt in confirmed_appts:
            # Combine date and time into datetime
            appt_datetime = timezone.make_aware(
                datetime.combine(appt.appointment_date, appt.appointment_time)
            )

            # Calculate time until appointment
            time_until = appt_datetime - now
            hours_until = time_until.total_seconds() / 3600

            # Check if we should send first reminder (closest to reminder_1_hours)
            if reminder_1_hours - 0.5 <= hours_until <= reminder_1_hours + 0.5:
                # Check if first reminder hasn't been sent
                if not Notification.objects.filter(
                    user=appt.user,
                    related_object_id=appt.id,
                    notification_type=Notification.NotificationType.APPOINTMENT_REMINDER_1,
                ).exists():
                    if send_appointment_reminder(appt, reminder_num=1):
                        # Customer reminder
                        if appt.user:
                            create_notification(
                                user=appt.user,
                                title='Appointment Reminder',
                                message=f'Your appointment for {appt.pet_name} is in {reminder_1_hours} hours',
                                notification_type=Notification.NotificationType.APPOINTMENT_REMINDER_1,
                                module_context=Notification.ModuleContext.APPOINTMENTS,
                                related_object_id=appt.id,
                                dedupe_window_minutes=180,
                            )

                        # Staff reminders (receptionists, vet assistants, and veterinarians)
                        if appt.branch:
                            for role_code in ['receptionist', 'vet_assistant', 'veterinarian']:
                                notify_role_users(
                                    role_code=role_code,
                                    branch=appt.branch,
                                    title=f'Upcoming Appointment: {appt.pet_name}',
                                    message=(
                                        f'Appointment for {appt.pet_name} is in {int(reminder_1_hours)} hours '
                                        f'at {appt.appointment_time.strftime("%I:%M %p")}'
                                    ),
                                    notification_type=Notification.NotificationType.APPOINTMENT_REMINDER_1,
                                    module_context=Notification.ModuleContext.APPOINTMENTS,
                                    related_object_id=appt.id,
                                )

                        reminders_sent += 1
                        self.stdout.write(self.style.SUCCESS(
                            f'Sent 1st reminder to {appt.owner_email} (Appt #{appt.id})'
                        ))

            # Check if we should send second reminder (closest to reminder_2_hours)
            if reminder_2_hours - 0.5 <= hours_until <= reminder_2_hours + 0.5:
                # Check if second reminder hasn't been sent
                if not Notification.objects.filter(
                    user=appt.user,
                    related_object_id=appt.id,
                    notification_type=Notification.NotificationType.APPOINTMENT_REMINDER_2,
                ).exists():
                    if send_appointment_reminder(appt, reminder_num=2):
                        # Customer reminder
                        if appt.user:
                            create_notification(
                                user=appt.user,
                                title='Appointment Reminder',
                                message=f'Your appointment for {appt.pet_name} is in {reminder_2_hours} hours',
                                notification_type=Notification.NotificationType.APPOINTMENT_REMINDER_2,
                                module_context=Notification.ModuleContext.APPOINTMENTS,
                                related_object_id=appt.id,
                                dedupe_window_minutes=180,
                            )

                        # Staff reminders (receptionists, vet assistants, and veterinarians)
                        if appt.branch:
                            for role_code in ['receptionist', 'vet_assistant', 'veterinarian']:
                                notify_role_users(
                                    role_code=role_code,
                                    branch=appt.branch,
                                    title=f'Appointment in {int(reminder_2_hours)} Hours: {appt.pet_name}',
                                    message=(
                                        f'Appointment for {appt.pet_name} is in {int(reminder_2_hours)} hours '
                                        f'at {appt.appointment_time.strftime("%I:%M %p")}'
                                    ),
                                    notification_type=Notification.NotificationType.APPOINTMENT_REMINDER_2,
                                    module_context=Notification.ModuleContext.APPOINTMENTS,
                                    related_object_id=appt.id,
                                )

                        reminders_sent += 1
                        self.stdout.write(self.style.SUCCESS(
                            f'Sent 2nd reminder to {appt.owner_email} (Appt #{appt.id})'
                        ))

        self.stdout.write(self.style.SUCCESS(
            f'Successfully sent {reminders_sent} reminder emails.'))
