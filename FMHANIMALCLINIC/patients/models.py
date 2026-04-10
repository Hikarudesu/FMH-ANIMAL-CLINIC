from django.db import models
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

from utils.validators import validate_image_file, IMAGE_UPLOAD_HELP_TEXT


class Pet(models.Model):
    """A pet that may belong to a registered portal user (owner) or a walk-in guest."""

    class Sex(models.TextChoices):
        MALE = 'MALE', 'Male'
        FEMALE = 'FEMALE', 'Female'

    class ClinicalStatus(models.TextChoices):
        HEALTHY = 'HEALTHY', 'Healthy'
        MONITOR = 'MONITOR', 'Under Monitoring'
        TREATMENT = 'TREATMENT', 'In Treatment'
        SURGERY = 'SURGERY', 'In Surgery'
        DIAGNOSTICS = 'DIAGNOSTICS', 'Pending Diagnostics'
        CRITICAL = 'CRITICAL', 'Critical'

    class Source(models.TextChoices):
        PORTAL = 'PORTAL', 'Portal (Registered User)'
        WALKIN = 'WALKIN', 'Walk-in (Guest)'

    # Registered portal user — nullable for walk-in / unregistered owners
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pets',
    )

    # Guest owner contact info — used when owner is null (walk-in)
    guest_owner_name = models.CharField(
        max_length=200, blank=True,
        verbose_name='Owner Name',
        help_text='Full name of the owner (for walk-in patients without an account)')
    guest_owner_phone = models.CharField(
        max_length=20, blank=True,
        verbose_name='Owner Phone',
        help_text='Contact number for the owner')
    guest_owner_email = models.EmailField(
        blank=True,
        verbose_name='Owner Email',
        help_text='Email address for the owner')
    guest_owner_address = models.TextField(
        blank=True,
        verbose_name='Owner Address',
        help_text='Full address of the owner')

    source = models.CharField(
        max_length=10,
        choices=Source.choices,
        default=Source.PORTAL,
        help_text='Whether this patient was registered via the portal or as a walk-in.',
    )

    name = models.CharField(max_length=100)
    species = models.CharField(max_length=60, help_text='e.g. Dog, Cat, Bird, Rabbit')
    breed = models.CharField(max_length=100, blank=True)
    date_of_birth = models.DateField(
        null=True,
        blank=True,
        help_text='Date of birth',
        verbose_name='Date of Birth'
    )
    sex = models.CharField(max_length=10, choices=Sex.choices)
    color = models.CharField(max_length=60, blank=True)
    photo = models.ImageField(
        upload_to='pet_photos/',
        blank=True,
        null=True,
        validators=[validate_image_file],
        help_text=IMAGE_UPLOAD_HELP_TEXT
    )
    
    # Clinical status - using ForeignKey for dynamic statuses
    clinical_status = models.ForeignKey(
        'settings.ClinicalStatus',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pets',
        help_text='Current clinical status of the pet',
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text='Inactive pets will not show in appointment dropdowns but keep their medical history.',
        verbose_name='Active Status'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['owner']),
            models.Index(fields=['name']),
            models.Index(fields=['is_active']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        owner_label = self.owner.username if self.owner else (self.guest_owner_name or 'Guest')
        return f'{self.name} ({self.species}) — {owner_label}'

    @property
    def status_display(self):
        """Get the display name for the clinical status."""
        if self.clinical_status:
            return self.clinical_status.name
        return 'Healthy'

    @property
    def status_color(self):
        """Get the color for the clinical status."""
        if self.clinical_status:
            return self.clinical_status.color
        return '#757575'

    @property
    def status(self):
        """Backward-compatible status code."""
        if self.clinical_status:
            return self.clinical_status.code
        return self.ClinicalStatus.HEALTHY

    @status.setter
    def status(self, value):
        """Backward-compatible status setter mapping to clinical_status FK."""
        if not value:
            self.clinical_status = None
            return
        try:
            from settings.models import ClinicalStatus
            self.clinical_status = ClinicalStatus.objects.get(code=value)
        except (ClinicalStatus.DoesNotExist, ObjectDoesNotExist):
            pass

    def get_status_display(self):
        """Backward-compatible display helper."""
        return self.status_display

    # ── Resolved owner helpers ─────────────────────────────────────────────
    @property
    def owner_display_name(self):
        """Returns the owner's display name regardless of portal/walk-in."""
        if self.owner:
            return self.owner.get_full_name() or self.owner.username
        return self.guest_owner_name or '—'

    @property
    def owner_display_phone(self):
        """Returns the owner's phone regardless of portal/walk-in."""
        if self.owner:
            return self.owner.phone_number or '—'
        return self.guest_owner_phone or '—'

    @property
    def owner_display_email(self):
        """Returns the owner's email regardless of portal/walk-in."""
        if self.owner:
            return self.owner.email or '—'
        return self.guest_owner_email or '—'

    @property
    def owner_display_address(self):
        """Returns the owner's address regardless of portal/walk-in."""
        if self.owner:
            return self.owner.address or '—'
        return self.guest_owner_address or '—'

    @property
    def is_walkin(self):
        """True when this patient has no linked portal account."""
        return self.source == self.Source.WALKIN or self.owner is None

    @property
    def has_missing_details(self):
        """Check if pet is missing important details (breed, date_of_birth, color)."""
        return not self.breed or not self.date_of_birth or not self.color

    @property
    def missing_details_list(self):
        """Return list of missing important details."""
        missing = []
        if not self.breed:
            missing.append('Breed')
        if not self.date_of_birth:
            missing.append('Date of Birth')
        if not self.color:
            missing.append('Color')
        return missing


# ── Signals: Sync Pet updates back to Appointments ────────────────────────────

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=Pet)
def sync_pet_to_appointments(sender, instance, **kwargs):
    """
    When a Pet record is updated, sync the changes back to all related Appointments
    to keep denormalized appointment data up-to-date.

    This ensures that if a pet's name, breed, or owner info is updated in the
    patient management system, all past and future appointments reflect the change.
    """
    # Import here to avoid circular import
    from appointments.models import Appointment

    # Find all appointments linked to this pet
    appointments = Appointment.objects.filter(pet=instance)

    if not appointments.exists():
        return

    # Prepare update fields
    updates = {
        'pet_name': instance.name,
        'pet_species': instance.species or '',
        'pet_breed': instance.breed or '',
        'pet_dob': instance.date_of_birth.isoformat() if instance.date_of_birth else '',
        'pet_sex': instance.sex,
        'pet_color': instance.color or '',
    }

    # For walk-in pets, also sync owner info
    if instance.is_walkin:
        updates.update({
            'owner_name': instance.guest_owner_name or '',
            'owner_phone': instance.guest_owner_phone or '',
            'owner_email': instance.guest_owner_email or '',
            'owner_address': instance.guest_owner_address or '',
        })
    # For portal pets, sync from the User model
    elif instance.owner:
        updates.update({
            'owner_name': instance.owner.get_full_name() or instance.owner.username,
            'owner_phone': instance.owner.phone_number or '',
            'owner_email': instance.owner.email or '',
            'owner_address': instance.owner.address or '',
        })

    # Bulk update all related appointments
    appointments.update(**updates)
