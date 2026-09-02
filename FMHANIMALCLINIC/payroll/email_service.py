"""Reliable, auditable payslip email delivery."""
from django.db import IntegrityError, transaction

from notifications.delivery import send_notification_email

from .models import PayslipEmailLog


def send_payslip_email(payslip, *, force=False):
    """Send one payslip and return ``(sent, reason)``.

    Successful sends are idempotent. Failed sends remain retryable.
    """
    recipient = (payslip.employee.email or '').strip().lower()
    if not recipient:
        return False, 'Employee has no email address.'

    if not force and PayslipEmailLog.objects.filter(
        payslip=payslip, recipient_email=recipient, status='SENT'
    ).exists():
        return True, 'Already sent.'

    period = payslip.payroll_period
    subject = f'Payslip for {period.period_display} - FMH Animal Clinic'
    message = f"""Dear {payslip.employee.full_name},

Your payslip for {period.period_display} has been released.

Gross Pay: ₱{payslip.gross_pay or 0:,.2f}
Net Pay: ₱{payslip.net_pay or 0:,.2f}

Please contact the Finance department if you have any questions.

Best regards,
FMH Animal Clinic
"""

    try:
        sent = send_notification_email(
            subject=subject,
            message=message.strip(),
            recipient_list=[recipient],
            fail_silently=False,
        )
        if not sent:
            raise RuntimeError('Email backend did not accept the message.')
    except Exception as exc:
        PayslipEmailLog.objects.create(
            payslip=payslip,
            recipient_email=recipient,
            status='FAILED',
            error_message=str(exc),
        )
        return False, str(exc)

    try:
        with transaction.atomic():
            PayslipEmailLog.objects.create(
                payslip=payslip,
                recipient_email=recipient,
                status='SENT',
            )
    except IntegrityError:
        if not PayslipEmailLog.objects.filter(
            payslip=payslip, recipient_email=recipient, status='SENT'
        ).exists():
            raise
        return True, 'Already sent.'

    return True, 'Sent.'