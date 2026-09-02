from django.core.management.base import BaseCommand
from django.utils import timezone

from reports.models import ScheduledReport
from reports.report_service import send_scheduled_report


class Command(BaseCommand):
    help = 'Send due scheduled reports once.'

    def handle(self, *args, **options):
        sent = failed = 0
        for report in ScheduledReport.objects.filter(is_active=True, next_run_at__lte=timezone.now()):
            ok, reason = send_scheduled_report(report)
            if ok:
                sent += 1
            else:
                failed += 1
                self.stderr.write(f'{report.name}: {reason}')
        self.stdout.write(f'Scheduled reports: sent={sent} failed={failed}')