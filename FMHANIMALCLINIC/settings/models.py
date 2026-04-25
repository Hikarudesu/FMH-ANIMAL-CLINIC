"""Models for the settings."""

import json
from decimal import Decimal

from django.db import models

from utils.validators import validate_image_file, IMAGE_UPLOAD_HELP_TEXT


class SystemSetting(models.Model):
    """
    Key-value store for system settings with type coercion support.
    """

    class Category(models.TextChoices):
        """Categories for grouping settings."""
        CLINIC = 'CLINIC', 'Clinic Information'
        APPOINTMENT = 'APPOINTMENT', 'Appointment Settings'
        INVENTORY = 'INVENTORY', 'Inventory Settings'
        NOTIFICATION = 'NOTIFICATION', 'Notification Settings'
        PAYROLL = 'PAYROLL', 'Payroll Settings'
        SYSTEM = 'SYSTEM', 'System Settings'
        MEDICAL = 'MEDICAL', 'Medical Records Settings'

    class ValueType(models.TextChoices):
        """Data types for setting values."""
        STRING = 'string', 'String'
        INTEGER = 'integer', 'Integer'
        BOOLEAN = 'boolean', 'Boolean'
        DECIMAL = 'decimal', 'Decimal'
        JSON = 'json', 'JSON'

    key = models.CharField(max_length=100, unique=True, primary_key=True)
    value = models.TextField(blank=True, null=True)
    value_type = models.CharField(
        max_length=20,
        choices=ValueType.choices,
        default=ValueType.STRING
    )
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.SYSTEM
    )
    description = models.TextField(blank=True)
    is_sensitive = models.BooleanField(
        default=False,
        help_text='Mark as sensitive for API keys, passwords, etc.'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'key']
        verbose_name = 'System Setting'
        verbose_name_plural = 'System Settings'

    def __str__(self):
        return f"{self.key} ({self.get_category_display()})"

    def get_typed_value(self):
        """
        Return the value converted to its proper Python type.
        """
        if self.value is None or self.value == '':
            return self._get_default_for_type()

        if self.value_type == self.ValueType.INTEGER:
            try:
                return int(self.value)
            except (ValueError, TypeError):
                return 0

        if self.value_type == self.ValueType.BOOLEAN:
            return self.value.lower() in ('true', '1', 'yes', 'on')

        if self.value_type == self.ValueType.DECIMAL:
            try:
                return Decimal(self.value)
            except (ValueError, TypeError):
                return Decimal('0')

        if self.value_type == self.ValueType.JSON:
            try:
                return json.loads(self.value)
            except (json.JSONDecodeError, TypeError):
                return {}

        # Default to string
        return self.value

    def set_typed_value(self, value):
        """
        Set the value from a Python type, converting to string for storage.
        """
        if isinstance(value, bool):
            self.value = 'true' if value else 'false'
            self.value_type = self.ValueType.BOOLEAN
        elif isinstance(value, int):
            self.value = str(value)
            self.value_type = self.ValueType.INTEGER
        elif isinstance(value, (float, Decimal)):
            self.value = str(value)
            self.value_type = self.ValueType.DECIMAL
        elif isinstance(value, (dict, list)):
            self.value = json.dumps(value)
            self.value_type = self.ValueType.JSON
        else:
            self.value = str(value) if value is not None else ''
            self.value_type = self.ValueType.STRING

    def _get_default_for_type(self):
        """Return default value based on value_type."""
        defaults = {
            self.ValueType.INTEGER: 0,
            self.ValueType.BOOLEAN: False,
            self.ValueType.DECIMAL: Decimal('0'),
            self.ValueType.JSON: {},
            self.ValueType.STRING: '',
        }
        return defaults.get(self.value_type, '')


class ClinicProfile(models.Model):
    """
    Singleton model for clinic branding and identity.
    Only one instance should exist (pk=1).
    """

    name = models.CharField(
        max_length=200,
        default='FMH Animal Clinic',
        help_text='Clinic display name'
    )
    logo = models.ImageField(
        upload_to='image/',
        blank=True,
        null=True,
        validators=[validate_image_file],
        help_text=IMAGE_UPLOAD_HELP_TEXT
    )
    email = models.EmailField(
        blank=True,
        help_text='Primary contact email'
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        help_text='Primary phone number'
    )
    address = models.TextField(
        blank=True,
        help_text='Main clinic address'
    )
    clinic_title = models.CharField(
        max_length=255,
        blank=True,
        help_text='Main landing-page title displayed beside the logo'
    )
    clinic_slogan = models.CharField(
        max_length=255,
        blank=True,
        help_text='Short landing-page slogan displayed under the title'
    )
    hero_description = models.TextField(
        blank=True,
        help_text='Landing-page hero description text'
    )
    license_number = models.CharField(
        max_length=100,
        blank=True,
        help_text='Business or veterinary license number'
    )
    facebook_url = models.URLField(blank=True, help_text='Facebook profile/page URL')
    instagram_url = models.URLField(blank=True, help_text='Instagram profile URL')
    messenger_url = models.URLField(blank=True, help_text='Messenger link URL')
    tiktok_url = models.URLField(blank=True, help_text='TikTok profile URL')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Clinic Profile'
        verbose_name_plural = 'Clinic Profile'

    def __str__(self):
        return str(self.name)

    def save(self, *args, **kwargs):
        """Enforce singleton pattern - only allow pk=1."""
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Prevent deletion of the singleton instance."""
        raise ValueError("Cannot delete the clinic profile singleton instance.")

    @classmethod
    def get_instance(cls):
        """Get or create the singleton instance."""
        instance, _ = cls.objects.get_or_create(pk=1)
        return instance


# =============================================================================
# Content Management Models
# =============================================================================

class SectionContent(models.Model):
    """
    Stores editable text content for landing page sections.
    Uses a key-based approach for each section type.
    """

    class SectionType(models.TextChoices):
        HERO = 'HERO', 'Hero Section'
        MISSION = 'MISSION', 'Mission Section'
        VISION = 'VISION', 'Vision Section'
        SERVICES_INTRO = 'SERVICES_INTRO', 'Services Introduction'
        VETS_INTRO = 'VETS_INTRO', 'Veterinarians Introduction'
        CORE_VALUES_INTRO = 'CORE_VALUES_INTRO', 'Core Values Introduction'

    section_type = models.CharField(
        max_length=20,
        choices=SectionType.choices,
        unique=True,
        primary_key=True
    )
    title = models.CharField(max_length=255, blank=True)
    subtitle = models.CharField(max_length=500, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(
        upload_to='image/',
        blank=True,
        null=True,
        validators=[validate_image_file],
        help_text=IMAGE_UPLOAD_HELP_TEXT
    )
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Section Content'
        verbose_name_plural = 'Section Contents'

    def __str__(self):
        return str(self.get_section_type_display())


class HeroStat(models.Model):
    """
    Hero section statistics displayed below the hero description.
    Example: "3 Clinic Branches", "AI Diagnostic Support", "24/7 Online Booking"
    """

    value = models.CharField(
        max_length=50,
        help_text="The main stat value (e.g., '3', 'AI', '24/7')"
    )
    label = models.CharField(
        max_length=100,
        help_text="Description label (e.g., 'Clinic Branches')"
    )
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order']
        verbose_name = 'Hero Statistic'
        verbose_name_plural = 'Hero Statistics'

    def __str__(self):
        return f"{self.value} - {self.label}"


class CoreValue(models.Model):
    """
    Core values displayed on the landing page.
    Example: Compassion, Integrity, Commitment, Quality of Life
    """

    title = models.CharField(max_length=100)
    icon = models.CharField(
        max_length=50,
        default='bx-star',
        help_text="Boxicons class name (e.g., 'bx-heart', 'bx-anchor')"
    )
    description = models.TextField(
        blank=True,
        help_text='Optional description for the value'
    )
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order']
        verbose_name = 'Core Value'
        verbose_name_plural = 'Core Values'

    def __str__(self):
        return str(self.title)


class Service(models.Model):
    """
    Services offered by the clinic, displayed on the services page.
    """

    title = models.CharField(max_length=150)
    description = models.TextField()
    icon = models.CharField(
        max_length=50,
        default='bx-plus-medical',
        help_text="Boxicons class name (e.g., 'bx-injection', 'bx-bath')"
    )
    image = models.ImageField(
        upload_to='image/',
        blank=True,
        null=True,
        validators=[validate_image_file],
        help_text=IMAGE_UPLOAD_HELP_TEXT
    )
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order']
        verbose_name = 'Service'
        verbose_name_plural = 'Services'

    def __str__(self):
        return str(self.title)


class Veterinarian(models.Model):
    """
    Veterinarian profiles displayed on the About page.
    """

    name = models.CharField(max_length=200)
    title = models.CharField(
        max_length=100,
        help_text="Professional title (e.g., 'Senior Veterinarian')"
    )
    bio = models.TextField(help_text='Short biography')
    photo = models.ImageField(
        upload_to='image/',
        blank=True,
        null=True,
        validators=[validate_image_file],
        help_text=IMAGE_UPLOAD_HELP_TEXT
    )
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order']
        verbose_name = 'Veterinarian'
        verbose_name_plural = 'Veterinarians'

    def __str__(self):
        return f"Dr. {self.name}"


# =============================================================================
# Configurable Options Models
# =============================================================================

class ReasonForVisit(models.Model):
    """
    Configurable reasons for appointment visits.
    Replaces the hardcoded Appointment.Reason TextChoices.
    """

    name = models.CharField(
        max_length=100,
        help_text='Display name for this reason (e.g., "General Consultation")'
    )
    code = models.CharField(
        max_length=30,
        unique=True,
        help_text='Unique code for internal use (e.g., "GENERAL")'
    )
    description = models.TextField(
        blank=True,
        help_text='Optional description for staff reference'
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text='Display order (lower numbers appear first)'
    )
    is_active = models.BooleanField(
        default=True,
        help_text='Inactive reasons will not appear in booking forms'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'name']
        verbose_name = 'Reason for Visit'
        verbose_name_plural = 'Reasons for Visit'

    def __str__(self):
        return str(self.name)

    @classmethod
    def get_default(cls):
        """Get or create a default reason for visit."""
        default, _ = cls.objects.get_or_create(
            code='GENERAL',
            defaults={
                'name': 'General Consultation',
                'description': 'General health consultation or check-up',
                'order': 0,
            }
        )
        return default


class ClinicalStatus(models.Model):
    """
    Configurable clinical status options for pets/patients.
    Replaces the hardcoded Pet.ClinicalStatus TextChoices.
    """

    name = models.CharField(
        max_length=100,
        help_text='Display name for this status (e.g., "Healthy")'
    )
    code = models.CharField(
        max_length=30,
        unique=True,
        help_text='Unique code for internal use (e.g., "HEALTHY")'
    )
    description = models.TextField(
        blank=True,
        help_text='Optional description for staff reference'
    )
    color = models.CharField(
        max_length=20,
        default='#4caf50',
        help_text='Color code for visual indication (e.g., "#4caf50" for green)'
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text='Display order (lower numbers appear first)'
    )
    is_active = models.BooleanField(
        default=True,
        help_text='Inactive statuses will not appear in patient forms'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'name']
        verbose_name = 'Clinical Status'
        verbose_name_plural = 'Clinical Statuses'

    def __str__(self):
        return str(self.name)

    @classmethod
    def get_default(cls):
        """Get or create a default clinical status."""
        default, _ = cls.objects.get_or_create(
            code='HEALTHY',
            defaults={
                'name': 'Healthy',
                'description': 'Pet is in good health',
                'color': '#4caf50',
                'order': 0,
            }
        )
        return default


# =============================================================================
# Legal Document Models
# =============================================================================

class LegalDocument(models.Model):
    """
    Admin-managed legal documents (Terms of Service, Privacy Policy).
    Each document_type is unique — one entry per type.
    Content is editable via Django Admin.
    """

    class DocumentType(models.TextChoices):
        TERMS_OF_SERVICE = 'TOS', 'Terms of Service'
        PRIVACY_POLICY = 'PRIVACY', 'Privacy Policy'

    document_type = models.CharField(
        max_length=10,
        choices=DocumentType.choices,
        unique=True,
        help_text='Type of legal document',
    )
    title = models.CharField(
        max_length=255,
        help_text='Display title (e.g., "Terms of Service")',
    )
    content = models.TextField(
        help_text='Full document content (supports HTML formatting)',
    )
    version = models.CharField(
        max_length=20,
        default='1.0',
        help_text='Document version number',
    )
    is_active = models.BooleanField(
        default=True,
        help_text='Only active documents are shown to users',
    )
    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Legal Document'
        verbose_name_plural = 'Legal Documents'
        ordering = ['document_type']

    def __str__(self):
        return f'{self.get_document_type_display()} (v{self.version})'

    @classmethod
    def get_tos(cls):
        """Get the active Terms of Service document."""
        return cls.objects.filter(
            document_type=cls.DocumentType.TERMS_OF_SERVICE,
            is_active=True,
        ).first()

    @classmethod
    def get_privacy_policy(cls):
        """Get the active Privacy Policy document."""
        return cls.objects.filter(
            document_type=cls.DocumentType.PRIVACY_POLICY,
            is_active=True,
        ).first()

