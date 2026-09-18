"""Central notification delivery helpers.

Provides channel guards using system settings and shared sender metadata.
"""

import logging
from email.utils import formataddr

from django.conf import settings
from django.core.mail import EmailMessage

from settings.utils import get_setting

logger = logging.getLogger('fmh')


def _email_enabled():
    return bool(get_setting('notification_email_enabled', True))


def _from_header():
    from_email = get_setting('notification_from_email', 'noreply@fmhclinic.com')
    sender_name = get_setting('notification_sender_name', 'FMH Animal Clinic')
    return formataddr((sender_name, from_email))


def send_notification_email(
    subject,
    message,
    recipient_list,
    fail_silently=True,
    superuser_only=False,
    from_email=None,
    attachments=None,
):
    """Send notification email if enabled in settings.

    If ``superuser_only`` is true, recipients are restricted to active superusers.
    """
    if not _email_enabled():
        logger.info("Notification email skipped: email notifications are disabled.")
        return False

    recipients = [email for email in (recipient_list or []) if email]
    if superuser_only and recipients:
        from accounts.models import User

        recipients = list(
            User.objects.filter(is_active=True, is_superuser=True, email__in=recipients)
            .exclude(email='')
            .values_list('email', flat=True)
        )

    if not recipients:
        return False

    try:
        email = EmailMessage(
            subject=subject,
            body=message,
            from_email=from_email or _from_header(),
            to=recipients,
        )
        for attachment in attachments or []:
            email.attach(*attachment)
        sent_count = email.send(fail_silently=fail_silently)
        if sent_count != len(recipients):
            logger.warning(
                "Email backend accepted %s of %s recipients for subject '%s'.",
                sent_count,
                len(recipients),
                subject,
            )
            return False
        return True
    except Exception as exc:
        logger.warning("Failed to send notification email to %s: %s", recipients, exc)
        return False


