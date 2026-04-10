from django.db import models


class Branch(models.Model):
    """Represents a physical clinic location."""

    name = models.CharField(max_length=150, unique=True, help_text="Branch name (e.g. Downtown Clinic)")
    branch_code = models.CharField(max_length=50, unique=True, blank=True, null=True)

    # Contact
    phone_number = models.CharField(max_length=20)
    email = models.EmailField(blank=True, null=True)

    # Address
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    zip_code = models.CharField(max_length=20)

    # License
    clinic_license_number = models.CharField(
        max_length=100, blank=True,
        help_text='Clinic/branch registration or license number'
    )

    # Operations
    operating_hours = models.TextField(blank=True, null=True, help_text="e.g. Mon-Fri: 8am-6pm, Sat: 9am-2pm")
    is_active = models.BooleanField(default=True)

    # Map Integration
    google_maps_embed_url = models.URLField(
        max_length=1000,
        blank=True,
        help_text='Google Maps embed URL for iframe display'
    )
    google_maps_link = models.URLField(
        max_length=500,
        blank=True,
        help_text='Direct link to Google Maps location'
    )

    # Social Media Links
    facebook_url = models.URLField(max_length=500, blank=True, help_text='Facebook page URL')
    instagram_url = models.URLField(max_length=500, blank=True, help_text='Instagram profile URL')
    messenger_url = models.URLField(max_length=500, blank=True, help_text='Facebook Messenger URL')
    tiktok_url = models.URLField(max_length=500, blank=True, help_text='TikTok profile URL')

    # Display Settings for Landing Page
    display_order = models.PositiveIntegerField(
        default=0,
        help_text='Order for contact page display (lower = first)'
    )
    badge_label = models.CharField(
        max_length=50,
        blank=True,
        help_text="Display badge (e.g., 'Main Branch', 'New!')"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Branches'
        ordering = ['name']

    def __str__(self):
        return f'{self.name} — {self.city}'
