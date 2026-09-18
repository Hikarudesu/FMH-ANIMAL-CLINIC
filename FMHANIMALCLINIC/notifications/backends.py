"""SMTP backend that avoids unreachable IPv6 routes on some hosts."""

import smtplib
import socket
import json
import base64
from urllib import error, request

from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.backends.smtp import EmailBackend
from django.conf import settings


class BrevoAPIEmailBackend(BaseEmailBackend):
    """Send transactional email through Brevo's HTTPS API."""

    api_url = 'https://api.brevo.com/v3/smtp/email'

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        sent_count = 0
        for email_message in email_messages:
            if self._send_message(email_message):
                sent_count += 1
        return sent_count

    def _send_message(self, email_message):
        recipients = email_message.recipients()
        if not recipients:
            return False

        sender = email_message.from_email or settings.DEFAULT_FROM_EMAIL
        sender_name, sender_email = self._split_sender(sender)
        payload = {
            'sender': {'name': sender_name, 'email': sender_email},
            'to': [{'email': recipient} for recipient in recipients],
            'subject': email_message.subject,
            'textContent': email_message.body,
        }
        if email_message.attachments:
            payload['attachment'] = [
                {
                    'name': filename,
                    'content': base64.b64encode(content).decode('ascii'),
                }
                for filename, content, _ in email_message.attachments
            ]
        api_request = request.Request(
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
            with request.urlopen(api_request, timeout=settings.EMAIL_TIMEOUT) as response:
                if response.status not in (200, 201, 202):
                    raise RuntimeError(f'Brevo API returned HTTP {response.status}')
            return True
        except (OSError, error.HTTPError, RuntimeError):
            if not self.fail_silently:
                raise
            return False

    @staticmethod
    def _split_sender(sender):
        if '<' in sender and sender.endswith('>'):
            name, email = sender.rsplit('<', 1)
            return name.strip(), email[:-1].strip()
        return 'FMH Animal Clinic', sender.strip()


class IPv4SMTPEmailBackend(EmailBackend):
    """Connect to the configured SMTP host using an IPv4 address."""

    def open(self):
        if self.connection:
            return False

        try:
            addresses = socket.getaddrinfo(
                self.host,
                self.port,
                family=socket.AF_INET,
                type=socket.SOCK_STREAM,
            )
            if not addresses:
                raise OSError(f'No IPv4 address found for {self.host}')

            ipv4_address = addresses[0][4][0]
            connection = smtplib.SMTP(timeout=self.timeout)
            connection.connect(ipv4_address, self.port)

            # Keep the hostname for Gmail TLS certificate/SNI validation.
            connection._host = self.host  # pylint: disable=protected-access

            if self.use_tls:
                connection.starttls(context=self.ssl_context)
            if self.username and self.password:
                connection.login(self.username, self.password)

            self.connection = connection
            return True
        except OSError:
            if not self.fail_silently:
                raise
            return False
        except smtplib.SMTPException:
            if not self.fail_silently:
                raise
            return False