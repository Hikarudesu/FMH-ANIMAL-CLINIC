"""Generate and deliver scheduled report summaries."""
import csv
from datetime import timedelta
from io import StringIO

from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone

from appointments.models import Appointment
from patients.models import Pet
from pos.models import Sale

from .models import ScheduledReportDelivery


def send_scheduled_report(report):
    now = timezone.now()
    period_key = now.strftime('%Y-%m-%d')
    if ScheduledReportDelivery.objects.filter(report=report, period_key=period_key, status='SENT').exists():
        return True, 'Already sent.'

    start = now - timedelta(days=1 if report.frequency == 'DAILY' else 7 if report.frequency == 'WEEKLY' else 30)
    sales = Sale.objects.filter(status=Sale.Status.COMPLETED, created_at__gte=start)
    appointments = Appointment.objects.filter(created_at__gte=start).exclude(status=Appointment.Status.CANCELLED)
    pets = Pet.objects.filter(created_at__gte=start)
    if report.branch_id:
        sales = sales.filter(branch_id=report.branch_id)
        appointments = appointments.filter(branch_id=report.branch_id)
        pets = pets.filter(branch_id=report.branch_id)

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(['Metric', 'Value', 'From', 'To'])
    writer.writerow(['Completed sales', sales.count(), start.isoformat(), now.isoformat()])
    writer.writerow(['Appointments', appointments.count(), start.isoformat(), now.isoformat()])
    writer.writerow(['New pets', pets.count(), start.isoformat(), now.isoformat()])
    recipients = [address.strip() for address in report.recipients.split(',') if address.strip()]
    if not recipients:
        return False, 'No recipients configured.'

    try:
        EmailMessage(
            subject=f'{report.name} - FMH Animal Clinic',
            body='Your scheduled clinic report is attached.',
            from_email=None,
            to=recipients,
            attachments=[('clinic-report.csv', buffer.getvalue(), 'text/csv')],
        ).send(fail_silently=False)
    except Exception as exc:
        ScheduledReportDelivery.objects.update_or_create(
            report=report, period_key=period_key,
            defaults={'recipients': ','.join(recipients), 'status': 'FAILED', 'error_message': str(exc)},
        )
        return False, str(exc)

    with transaction.atomic():
        ScheduledReportDelivery.objects.update_or_create(
            report=report, period_key=period_key,
            defaults={'recipients': ','.join(recipients), 'status': 'SENT', 'error_message': ''},
        )
        report.last_run_at = now
        report.next_run_at = now + timedelta(days=1 if report.frequency == 'DAILY' else 7 if report.frequency == 'WEEKLY' else 30)
        report.save(update_fields=['last_run_at', 'next_run_at'])
    return True, 'Sent.'