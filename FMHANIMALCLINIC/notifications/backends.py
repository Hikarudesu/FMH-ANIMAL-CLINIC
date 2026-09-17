"""Email backend for sending Django email through Brevo's HTTPS API."""

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger('fmh')


class BrevoEmailBackend(BaseEmailBackend):
    """Send Django messages through Brevo instead of SMTP."""

    api_url = 'https://api.brevo.com/v3/smtp/email'

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        sent_count = 0
        for message in email_messages:
            if self._send_message(message):
                sent_count += 1
        return sent_count

    def _send_message(self, message):
        recipients = [email for email in message.recipients() if email]
        if not recipients:
            return False

        payload = {
            'sender': {
                'email': message.from_email or settings.DEFAULT_FROM_EMAIL,
            },
            'to': [{'email': email} for email in recipients],
            'subject': message.subject,
            'textContent': message.body,
        }
        if message.extra_headers.get('Reply-To'):
            payload['replyTo'] = {'email': message.extra_headers['Reply-To']}

        request = Request(
            self.api_url,
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'accept': 'application/json',
                'api-key': settings.BREVO_API_KEY,
                'content-type': 'application/json',
            },
            method='POST',
        )

        try:
            with urlopen(request, timeout=settings.EMAIL_TIMEOUT) as response:
                if 200 <= response.status < 300:
                    return True
                logger.warning('Brevo returned HTTP %s while sending email.', response.status)
        except (HTTPError, URLError, OSError) as exc:
            if not self.fail_silently:
                raise
            logger.warning('Brevo email delivery failed: %s', exc)
        return False