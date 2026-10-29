"""Email delivery for customer inquiry responses."""

import logging

from django.conf import settings
from django.utils import timezone

from notifications.delivery import send_notification_email

logger = logging.getLogger('fmh')


def send_inquiry_response_email(inquiry):
    """Email the complete inquiry details and staff response to the customer."""
    if not inquiry.email or not inquiry.response.strip():
        return False

    branch_name = inquiry.branch.name if inquiry.branch else 'FMH Animal Clinic'
    responder = inquiry.responded_by
    responder_name = (
        responder.get_full_name() or responder.username
        if responder else 'Clinic staff'
    )
    response_date = inquiry.response_date or timezone.now()
    submitted_date = inquiry.created_at.astimezone(
        timezone.get_current_timezone()
    )
    internal_notes = inquiry.internal_notes.strip() or 'No additional notes.'

    message = (
        f'Dear {inquiry.full_name},\n\n'
        'Thank you for contacting FMH Animal Clinic. A member of our staff '
        'has responded to your inquiry.\n\n'
        'INQUIRY DETAILS\n'
        f'Name: {inquiry.full_name}\n'
        f'Email: {inquiry.email}\n'
        f'Phone: {inquiry.phone}\n'
        f'Branch: {branch_name}\n'
        f'Inquiry reference: #{inquiry.pk}\n'
        f'Submitted: {submitted_date:%B %d, %Y at %I:%M %p}\n'
        f'Priority: {inquiry.get_priority_display()}\n\n'
        'YOUR MESSAGE\n'
        f'{inquiry.message.strip()}\n\n'
        'STAFF RESPONSE\n'
        f'{inquiry.response.strip()}\n\n'
        'ADDITIONAL NOTES\n'
        f'{internal_notes}\n\n'
        f'Responded by: {responder_name}\n'
        f'Responded: {response_date.astimezone(timezone.get_current_timezone()):%B %d, %Y at %I:%M %p}\n\n'
        'If you need further assistance, please reply to this email or '
        f'contact {branch_name} directly.\n\n'
        'Sincerely,\n'
        'FMH Animal Clinic'
    )

    sent = send_notification_email(
        subject=f'FMH Animal Clinic Inquiry Response #{inquiry.pk}',
        message=message,
        recipient_list=[inquiry.email],
        from_email=settings.DEFAULT_FROM_EMAIL,
        fail_silently=False,
    )
    if not sent:
        logger.warning(
            'Inquiry response email was not delivered for inquiry %s.',
            inquiry.pk,
        )
    return sent
