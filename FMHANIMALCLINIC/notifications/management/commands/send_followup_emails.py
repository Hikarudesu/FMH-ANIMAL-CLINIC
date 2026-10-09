from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from notifications.followup_email_service import (
    send_follow_up_email,
    send_follow_up_reminder_email,
)
from notifications.models import FollowUp
from notifications.models import Notification
from notifications.utils import create_notification, get_follow_up_owner


class Command(BaseCommand):
    help = 'Send due follow-up reminder emails once.'

    def handle(self, *args, **options):
        today = timezone.localdate()
        reminder_date = today + timedelta(days=3)
        pending_followups = FollowUp.objects.filter(
            is_completed=False,
            email_sent_at__isnull=True,
            follow_up_date__gte=today,
        ).select_related('appointment', 'medical_record__pet__owner')
        followups = FollowUp.objects.filter(
            is_completed=False,
            reminder_email_sent_at__isnull=True,
            follow_up_date=reminder_date,
        ).select_related('appointment', 'medical_record__pet__owner')
        sent = failed = reminders_sent = 0
        for follow_up in pending_followups:
            ok, reason = send_follow_up_email(follow_up, event='scheduled')
            if ok:
                sent += 1
            else:
                failed += 1
                self.stderr.write(f'Follow-up #{follow_up.pk}: {reason}')

        for follow_up in followups:
            ok, reason = send_follow_up_reminder_email(follow_up)
            if ok:
                owner = get_follow_up_owner(follow_up.appointment)
                if owner:
                    create_notification(
                        user=owner,
                        title=f'Follow-up Reminder for {follow_up.pet_name}',
                        message=(
                            f'{follow_up.pet_name} has a follow-up visit in 3 days '
                            f'on {follow_up.follow_up_date}. '
                            f'Reason: {follow_up.reason or "Routine follow-up"}.'
                        ),
                        notification_type=Notification.NotificationType.FOLLOW_UP,
                        module_context=Notification.ModuleContext.APPOINTMENTS,
                        related_object_id=follow_up.appointment_id,
                        related_follow_up=follow_up,
                    )
                reminders_sent += 1
            else:
                failed += 1
                self.stderr.write(f'Follow-up #{follow_up.pk}: {reason}')
        self.stdout.write(
            f'Follow-up emails: sent={sent} failed={failed}; '
            f'reminders sent={reminders_sent}'
        )