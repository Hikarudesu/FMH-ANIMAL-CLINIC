"""OTP (One-Time Password) model for password reset flows."""

import random
import string
from datetime import timedelta

from django.db import models
from django.conf import settings
from django.utils import timezone


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
        max_length=6,
        help_text='6-digit OTP code',
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
            models.Index(fields=['otp_code', 'is_used']),
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
        otp_code = ''.join(random.choices(string.digits, k=6))

        # Create new token (expires in 10 minutes)
        token = cls.objects.create(
            user=user,
            otp_code=otp_code,
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        return token

    @classmethod
    def verify(cls, email, otp_code):
        """
        Verify an OTP code for a user identified by email.
        Returns the user if valid, None otherwise.
        """
        from accounts.models import User

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return None

        token = cls.objects.filter(
            user=user,
            otp_code=otp_code,
            is_used=False,
        ).order_by('-created_at').first()

        if token and token.is_valid():
            return user

        return None
