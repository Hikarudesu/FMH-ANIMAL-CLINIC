"""OTP (One-Time Password) model for password reset flows."""

import secrets
import string
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.db import models, transaction
from django.conf import settings
from django.utils import timezone
from django.utils.crypto import constant_time_compare


class OTPToken(models.Model):
    """
    Stores one-time password tokens for password reset.
    Tokens expire after 10 minutes and can only be used once.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='otp_tokens',
    )
    otp_code = models.CharField(
        max_length=128,
        help_text='One-way OTP verifier; the original code is not stored.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'OTP Token'
        verbose_name_plural = 'OTP Tokens'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        return f'OTP for {self.user.username} — {"Used" if self.is_used else "Active"}'

    def is_valid(self):
        """Check if the OTP is still valid (not expired and not used)."""
        return not self.is_used and timezone.now() < self.expires_at

    def mark_used(self):
        """Mark this OTP as used."""
        self.is_used = True
        self.save(update_fields=['is_used'])

    @property
    def delivery_code(self):
        """Return the plaintext code only on the object that generated it."""
        return getattr(self, '_delivery_code', '')

    def matches_code(self, submitted_code):
        """Verify new password-hashed tokens and legacy plaintext tokens."""
        if self.otp_code.isdigit() and len(self.otp_code) == 6:
            return constant_time_compare(self.otp_code, submitted_code)
        return check_password(submitted_code, self.otp_code)

    @classmethod
    def generate(cls, user):
        """
        Generate a new OTP for the given user.
        Invalidates all previous unused OTPs for this user.
        Returns the created OTPToken instance.
        """
        # Invalidate all previous unused OTPs for this user
        cls.objects.filter(user=user, is_used=False).update(is_used=True)

        # Generate 6-digit numeric OTP
        otp_code = ''.join(secrets.choice(string.digits) for _ in range(6))

        # Create new token (expires in 10 minutes)
        token = cls.objects.create(
            user=user,
            otp_code=make_password(otp_code),
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        token._delivery_code = otp_code
        return token

    @classmethod
    def verify(cls, email, otp_code):
        """
        Verify an OTP code for a user identified by email.
        Returns the user if valid, None otherwise.
        """
        from accounts.models import User

        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            return None

        token = cls.objects.filter(
            user=user,
            is_used=False,
            expires_at__gt=timezone.now(),
        ).order_by('-created_at').first()

        if token and token.matches_code(otp_code):
            return user

        return None

    @classmethod
    def verify_and_consume(cls, email, otp_code):
        """Atomically verify and mark a matching code used exactly once."""
        from accounts.models import User

        with transaction.atomic():
            user = User.objects.filter(email__iexact=email).first()
            if user is None:
                return None

            token = cls.objects.select_for_update().filter(
                user=user,
                is_used=False,
                expires_at__gt=timezone.now(),
            ).order_by('-created_at').first()
            if token and token.matches_code(otp_code):
                token.mark_used()
                return user

        return None
