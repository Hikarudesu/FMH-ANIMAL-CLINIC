from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from notifications.followup_email_service import send_follow_up_email
from notifications.models import FollowUp


class Command(BaseCommand):
    help = 'Send due follow-up reminder emails once.'

    def handle(self, *args, **options):
        today = timezone.localdate()
        followups = FollowUp.objects.filter(
            is_completed=False,
            email_sent_at__isnull=True,
            follow_up_date__gte=today,
            follow_up_date__lte=today + timedelta(days=1),
        ).select_related('appointment')
        sent = failed = 0
        for follow_up in followups:
            ok, reason = send_follow_up_email(follow_up)
            if ok:
                sent += 1
            else:
                failed += 1
                self.stderr.write(f'Follow-up #{follow_up.pk}: {reason}')
        self.stdout.write(f'Follow-up emails: sent={sent} failed={failed}')