"""Central notification delivery helpers.

Provides channel guards using system settings and shared sender metadata.
"""

import logging
import re
from email.utils import formataddr

from django.core.mail import send_mail

from settings.utils import get_setting

logger = logging.getLogger('fmh')


def _email_enabled():
    return bool(get_setting('notification_email_enabled', True))


def _sms_enabled():
    return bool(get_setting('notification_sms_enabled', False))


def _from_header():
    from_email = get_setting('notification_from_email', 'noreply@fmhclinic.com')
    sender_name = get_setting('notification_sender_name', 'FMH Animal Clinic')
    return formataddr((sender_name, from_email))


def normalize_ph_sim_number(raw_number):
    """Normalize PH mobile numbers to E.164 (+63XXXXXXXXXX).

    Accepted inputs:
    - 09XXXXXXXXX
    - 9XXXXXXXXX
    - 639XXXXXXXXX
    - +639XXXXXXXXX
    """
    if not raw_number:
        return ''

    cleaned = re.sub(r'[^\d+]', '', str(raw_number).strip())
    digits = re.sub(r'\D', '', cleaned)

    if digits.startswith('09') and len(digits) == 11:
        return f'+63{digits[1:]}'
    if digits.startswith('9') and len(digits) == 10:
        return f'+63{digits}'
    if digits.startswith('639') and len(digits) == 12:
        return f'+{digits}'
    if cleaned.startswith('+639') and len(digits) == 12:
        return f'+{digits}'

    return ''


def send_notification_email(subject, message, recipient_list, fail_silently=True, superuser_only=False):
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
        send_mail(
            subject=subject,
            message=message,
            from_email=_from_header(),
            recipient_list=recipients,
            fail_silently=fail_silently,
        )
        return True
    except Exception as exc:
        logger.warning("Failed to send notification email to %s: %s", recipients, exc)
        return False


def send_notification_sms(message, sim_number=None):
    """Send SMS notification if enabled.

    This project currently stores a PH default SIM number and normalizes it to +63
    format. Actual gateway/modem integration can be plugged in here later.
    """
    if not _sms_enabled():
        logger.info("Notification SMS skipped: SMS notifications are disabled.")
        return False

    default_sim = get_setting('notification_sms_default_recipient', '')
    target = sim_number or default_sim
    normalized = normalize_ph_sim_number(target)

    if not normalized:
        logger.warning("Notification SMS skipped: invalid PH SIM number '%s'.", target)
        return False

    logger.info("SMS dispatch placeholder to %s: %s", normalized, message)
    return True
