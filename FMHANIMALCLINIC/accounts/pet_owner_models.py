"""PetOwner profile model — extends User for pet-owner-specific data."""

from django.db import models
from django.conf import settings


class PetOwner(models.Model):
    """
    Profile model for Pet Owners (clients).
    Automatically created when a non-staff user registers.
    Provides pet-owner-specific fields separate from staff data.
    """

    class PreferredCommunication(models.TextChoices):
        EMAIL = 'EMAIL', 'Email'
        SMS = 'SMS', 'SMS'
        PHONE = 'PHONE', 'Phone Call'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='pet_owner_profile',
        help_text='Linked user account',
    )

    # Emergency contact
    emergency_contact_name = models.CharField(
        max_length=200, blank=True,
        help_text='Emergency contact person name',
    )
    emergency_contact_phone = models.CharField(
        max_length=20, blank=True,
        help_text='Emergency contact phone number',
    )

    # Preferences
    preferred_communication = models.CharField(
        max_length=10,
        choices=PreferredCommunication.choices,
        default=PreferredCommunication.EMAIL,
        help_text='Preferred method of communication',
    )

    # Internal notes (staff-facing)
    notes = models.TextField(
        blank=True,
        help_text='Internal notes about this pet owner (visible to staff only)',
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Pet Owner Profile'
        verbose_name_plural = 'Pet Owner Profiles'
        ordering = ['user__last_name', 'user__first_name']

    def __str__(self):
        return f'{self.user.get_full_name() or self.user.username} — Pet Owner Profile'

    @property
    def full_name(self):
        """Return the linked user's full name."""
        return self.user.get_full_name() or self.user.username

    @property
    def email(self):
        """Proxy to user email."""
        return self.user.email

    @property
    def phone(self):
        """Proxy to user phone."""
        return self.user.phone_number

    @property
    def pet_count(self):
        """Return number of pets owned."""
        return self.user.pets.count()
