"""Create and deliver durable PDF archives when a branch is deactivated."""

import io

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from xhtml2pdf import pisa

from notifications.delivery import send_notification_email
from payroll.models import PayrollPeriod
from pos.models import Sale

from .models import BranchArchive


def _build_branch_archive_pdf(branch):
    sales = list(
        Sale.objects.filter(branch=branch)
        .select_related('customer', 'pet', 'cashier')
        .prefetch_related('items')
        .order_by('created_at', 'pk')
    )
    payroll_periods = list(
        PayrollPeriod.objects.filter(
            branch=branch,
            status__in=(PayrollPeriod.Status.GENERATED, PayrollPeriod.Status.RELEASED),
        ).order_by('year', 'month', 'period_type')
    )
    for period in payroll_periods:
        period.archive_payslips = list(
            period.payslips.select_related('employee').order_by('employee__last_name', 'employee__first_name')
        )

    html = render_to_string('branches/branch_archive_pdf.html', {
        'branch': branch,
        'generated_at': timezone.now(),
        'sales': sales,
        'payroll_periods': payroll_periods,
    })
    result = io.BytesIO()
    pdf = pisa.pisaDocument(io.BytesIO(html.encode('utf-8')), result)
    if pdf.err:
        raise RuntimeError('Could not generate the branch history PDF.')
    return result.getvalue(), len(sales), len(payroll_periods)


def create_branch_archive(branch):
    """Save a branch sales/payroll PDF and enqueue administrator delivery."""
    pdf_content, sale_count, payroll_period_count = _build_branch_archive_pdf(branch)
    recipients = list(
        get_user_model().objects.filter(
            is_active=True,
            is_superuser=True,
        ).exclude(email='').values_list('email', flat=True)
    )
    archive = BranchArchive.objects.create(
        branch=branch,
        sale_count=sale_count,
        payroll_period_count=payroll_period_count,
        recipient_emails=recipients,
    )
    filename = f'branch_{branch.pk}_archive_{archive.pk}.pdf'
    archive.pdf_file.save(filename, ContentFile(pdf_content), save=True)
    transaction.on_commit(
        lambda archive_id=archive.pk: deliver_branch_archive_email(archive_id)
    )
    return archive


def deliver_branch_archive_email(archive_id):
    """Send a saved archive; failed deliveries remain available for retry."""
    archive = BranchArchive.objects.select_related('branch').get(pk=archive_id)
    if archive.email_status == BranchArchive.EmailStatus.SENT:
        return True

    recipients = archive.recipient_emails
    if not recipients:
        archive.email_status = BranchArchive.EmailStatus.FAILED
        archive.email_error = 'No active superuser email addresses are registered.'
        archive.save(update_fields=['email_status', 'email_error'])
        return False

    try:
        with archive.pdf_file.open('rb') as pdf_file:
            pdf_content = pdf_file.read()
        sent = send_notification_email(
            subject=f"{archive.branch.name} branch history archive",
            message=(
                f"The attached PDF contains the sales and payroll history for "
                f"{archive.branch.name}, archived when the branch was deactivated."
            ),
            recipient_list=recipients,
            superuser_only=True,
            fail_silently=False,
            from_email=settings.DEFAULT_FROM_EMAIL,
            attachments=[(
                archive.pdf_file.name.rsplit('/', 1)[-1],
                pdf_content,
                'application/pdf',
            )],
        )
        if not sent:
            raise RuntimeError('Email backend did not accept the archive message.')
    except Exception as exc:
        archive.email_status = BranchArchive.EmailStatus.FAILED
        archive.email_error = str(exc)
        archive.save(update_fields=['email_status', 'email_error'])
        return False

    archive.email_status = BranchArchive.EmailStatus.SENT
    archive.email_error = ''
    archive.sent_at = timezone.now()
    archive.save(update_fields=['email_status', 'email_error', 'sent_at'])
    return True