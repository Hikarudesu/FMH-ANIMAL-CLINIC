"""SMTP backend that avoids unreachable IPv6 routes on some hosts."""

import smtplib
import socket

from django.core.mail.backends.smtp import EmailBackend


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