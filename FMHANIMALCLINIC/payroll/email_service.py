"""Reliable, auditable payslip email delivery."""
import io
import base64

from django.conf import settings
from django.db import IntegrityError, transaction
from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from xhtml2pdf import pisa

from notifications.delivery import send_notification_email

from .models import PayslipEmailLog


def _pdf_link_callback(uri, rel):
    """Resolve static assets used by the printable payslip template."""
    static_url = settings.STATIC_URL
    if uri.startswith(static_url):
        path = finders.find(uri[len(static_url):])
        if path:
            return path
    return uri


def _build_payslip_pdf(payslip):
    logo_path = finders.find('image/PAYSLIP-LOGO.png')
    logo_data_uri = ''
    if logo_path:
        with open(logo_path, 'rb') as logo_file:
            logo_data_uri = 'data:image/png;base64,' + base64.b64encode(
                logo_file.read()
            ).decode('ascii')

    earnings = []
    if payslip.base_salary > 0:
        earnings.append(('Base Salary', payslip.base_salary))
    if payslip.overtime_pay > 0:
        earnings.append((f'Overtime Pay ({payslip.overtime_hours} hrs)', payslip.overtime_pay))
    if payslip.holiday_pay > 0:
        earnings.append(('Holiday Pay', payslip.holiday_pay))
    if payslip.bonus > 0:
        earnings.append(('Bonus', payslip.bonus))
    if payslip.staff_allowance > 0:
        earnings.append(('Staff Allowance', payslip.staff_allowance))

    deductions = []
    if payslip.sss > 0:
        deductions.append(('SSS Contribution', payslip.sss))
    if payslip.philhealth > 0:
        deductions.append(('PhilHealth Contribution', payslip.philhealth))
    if payslip.pagibig > 0:
        deductions.append(('Pag-IBIG Contribution', payslip.pagibig))
    if payslip.late_deduction > 0:
        deductions.append(('Late / Undertime', payslip.late_deduction))
    if payslip.absent_deduction > 0:
        deductions.append(('Absences', payslip.absent_deduction))
    if payslip.other_deductions > 0:
        deductions.append(('Imported Charges', payslip.other_deductions))
    deductions.extend(
        (deduction.reason, deduction.amount)
        for deduction in payslip.custom_deductions.all()
    )
    if not deductions:
        deductions.append(('No deductions this period', None))

    row_count = max(len(earnings), len(deductions)) + 2
    earnings.extend([('', None)] * (row_count - len(earnings)))
    deductions.extend([('', None)] * (row_count - len(deductions)))
    ledger_rows = list(zip(earnings, deductions))

    html = render_to_string('payroll/payslip_email_pdf.html', {
        'payslip': payslip,
        'ledger_rows': ledger_rows,
        'logo_data_uri': logo_data_uri,
    })
    result = io.BytesIO()
    pdf = pisa.pisaDocument(
        io.BytesIO(html.encode('utf-8')),
        result,
        link_callback=_pdf_link_callback,
    )
    if pdf.err:
        raise RuntimeError('Could not generate the printable payslip PDF.')
    return result.getvalue()


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

Your official payslip for {period.period_display} is attached as a PDF.

Please contact the Finance department if you have any questions.

Best regards,
FMH Animal Clinic
"""

    try:
        pdf_content = _build_payslip_pdf(payslip)
        sent = send_notification_email(
            subject=subject,
            message=message.strip(),
            recipient_list=[recipient],
            fail_silently=False,
            from_email=settings.DEFAULT_FROM_EMAIL,
            attachments=[(
                f'payslip_{payslip.id}_{period.year}_{period.month:02d}.pdf',
                pdf_content,
                'application/pdf',
            )],
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