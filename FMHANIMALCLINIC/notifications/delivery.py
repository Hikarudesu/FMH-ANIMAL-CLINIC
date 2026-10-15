"""Central notification delivery helpers.

Provides channel guards using system settings and shared sender metadata.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMessage, send_mail

logger = logging.getLogger('fmh')


def _from_header():
    """Use the sender configured with the application's email backend."""
    return settings.DEFAULT_FROM_EMAIL


def send_notification_email(
    subject,
    message,
    recipient_list,
    fail_silently=True,
    superuser_only=False,
    from_email=None,
    attachments=None,
    force=False,
):
    """Send a notification email to the explicit recipients selected by its caller.

    If ``superuser_only`` is true, recipients are restricted to active superusers.
    ``force`` remains accepted for compatibility with existing call sites.
    """
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
        if not attachments:
            sent_count = send_mail(
                subject=subject,
                message=message,
                from_email=from_email or _from_header(),
                recipient_list=recipients,
                fail_silently=fail_silently,
            )
            if sent_count != len(recipients):
                logger.warning(
                    "Email backend accepted %s of %s recipients for subject '%s'.",
                    sent_count,
                    len(recipients),
                    subject,
                )
                return False
            return True

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

