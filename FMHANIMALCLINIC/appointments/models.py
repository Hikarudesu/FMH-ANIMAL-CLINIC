from datetime import datetime
from django.db import models
from django.utils import timezone
from branches.models import Branch
from employees.models import StaffMember


class Appointment(models.Model):
    """Represents a pet appointment / reservation."""

    class Source(models.TextChoices):
        WALKIN = 'WALKIN', 'Walk-in (Guest)'
        PORTAL = 'PORTAL', 'Portal (Registered User)'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        CANCELLED = 'CANCELLED', 'Cancelled'
        COMPLETED = 'COMPLETED', 'Completed'

    # Owner info
    owner_name = models.CharField(max_length=200)
    owner_email = models.EmailField(blank=True)
    owner_phone = models.CharField(max_length=20, blank=True)
    owner_address = models.TextField(blank=True, help_text='Full address of the owner')

    # Pet info
    pet_name = models.CharField(max_length=150)
    pet_species = models.CharField(max_length=60, blank=True, help_text='e.g. Dog, Cat, Bird')
    pet_breed = models.CharField(max_length=150, blank=True)
    pet_dob = models.CharField(max_length=50, blank=True, null=True, help_text='Date of birth (YYYY-MM-DD)')
    pet_sex = models.CharField(max_length=10, blank=True)
    pet_color = models.CharField(max_length=60, blank=True)
    pet_symptoms = models.TextField(
        blank=True, help_text='Specific symptoms recorded for this visit')

    # Optional link to a registered Pet profile (set for portal bookings)
    pet = models.ForeignKey(
        'patients.Pet',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='appointments',
        help_text='Link to a registered pet profile, if available.',
    )

    # Scheduling
    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        related_name='appointments',
    )
    preferred_vet = models.ForeignKey(
        StaffMember,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='appointments',
        limit_choices_to={'position': StaffMember.Position.VETERINARIAN},
    )
    appointment_date = models.DateField()
    appointment_time = models.TimeField()

    # Booking metadata - using ForeignKey for dynamic reasons
    reason_for_visit = models.ForeignKey(
        'settings.ReasonForVisit',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='appointments',
        help_text='Reason for the appointment visit',
    )
    source = models.CharField(
        max_length=10,
        choices=Source.choices,
        default=Source.WALKIN,
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    is_returning_customer = models.BooleanField(default=False)

    # Link to user account (set when logged-in user books)
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='appointments',
    )

    # Link to POS sale (set when appointment is billed)
    sale = models.ForeignKey(
        'pos.Sale',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='appointments',
        help_text='Linked sale transaction when appointment is billed',
    )

    notes = models.TextField(blank=True, help_text='Additional notes')

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-appointment_date', '-appointment_time']
        indexes = [
            models.Index(fields=['appointment_date', 'appointment_time']),
            models.Index(fields=['status']),
            models.Index(fields=['appointment_date', 'status']),
            models.Index(fields=['branch', 'appointment_date']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f'{self.pet_name} ({self.owner_name}) — {self.appointment_date} {self.appointment_time}'

    @property
    def reason_display(self):
        """Get the display name for the visit reason."""
        if self.reason_for_visit:
            return self.reason_for_visit.name
        return 'General Consultation'

    def time_display(self):
        """
        Display appointment time intelligently.
        Shows 'Morning' or 'Afternoon' for flexible time slots (09:00 or 14:00),
        regardless of whether a vet was assigned. Otherwise shows the actual time.
        """
        if not self.appointment_time:
            return ''

        # For flexible time slots, ALWAYS show "Morning" or "Afternoon"
        # even if a vet was auto-assigned
        # Morning = 08:00, Afternoon = 13:00
        if self.appointment_time.hour == 8 and self.appointment_time.minute == 0:
            return 'Morning'
        elif self.appointment_time.hour == 13 and self.appointment_time.minute == 0:
            return 'Afternoon'
        else:
            # For specific vet times, show the actual time
            return self.appointment_time.strftime('%I:%M %p')

    @property
    def appointment_time_display(self):
        """Property version of time_display for use in templates."""
        return self.time_display()

    @property
    def is_past(self):
        """Returns True if the appointment date+time has already passed."""
        now = timezone.now()
        appt_dt = timezone.make_aware(
            datetime.combine(self.appointment_date, self.appointment_time)
        )
        return appt_dt < now

    # ── Dynamic pet/owner data helpers ────────────────────────────────────
    @property
    def current_pet_name(self):
        """Get current pet name (prefers linked Pet over denormalized field)."""
        return self.pet.name if self.pet else self.pet_name

    @property
    def current_pet_species(self):
        """Get current pet species (prefers linked Pet over denormalized field)."""
        return self.pet.species if self.pet else self.pet_species

    @property
    def current_pet_breed(self):
        """Get current pet breed (prefers linked Pet over denormalized field)."""
        return self.pet.breed if self.pet else self.pet_breed

    @property
    def current_pet_dob(self):
        """Get current pet date of birth (prefers linked Pet)."""
        if self.pet and self.pet.date_of_birth:
            return self.pet.date_of_birth
        # Try to parse the string DOB field
        if self.pet_dob:
            from datetime import date as _date_cls
            try:
                return _date_cls.fromisoformat(str(self.pet_dob).strip())
            except (ValueError, TypeError):
                pass
        return None

    @property
    def current_pet_sex(self):
        """Get current pet sex (prefers linked Pet over denormalized field)."""
        return self.pet.sex if self.pet else self.pet_sex

    @property
    def current_pet_color(self):
        """Get current pet color (prefers linked Pet over denormalized field)."""
        return self.pet.color if self.pet else self.pet_color

    @property
    def current_owner_name(self):
        """Get current owner name (prefers User > linked Pet > denormalized field)."""
        if self.user:
            return self.user.get_full_name() or self.user.username
        if self.pet:
            return self.pet.owner_display_name
        return self.owner_name

    @property
    def current_owner_phone(self):
        """Get current owner phone (prefers User > linked Pet > denormalized field)."""
        if self.user:
            return self.user.phone_number or ''
        if self.pet:
            return self.pet.owner_display_phone
        return self.owner_phone

    @property
    def current_owner_email(self):
        """Get current owner email (prefers User > linked Pet > denormalized field)."""
        if self.user:
            return self.user.email or ''
        if self.pet:
            return self.pet.owner_display_email
        return self.owner_email

    @property
    def current_owner_address(self):
        """Get current owner address (prefers User > linked Pet > denormalized field)."""
        if self.user:
            return self.user.address or ''
        if self.pet:
            return self.pet.owner_display_address
        return self.owner_address

    @classmethod
    def cleanup_expired(cls):
        """Delete PENDING appointments that are 1+ day past their booked time."""
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(days=1)
        expired = cls.objects.filter(
            appointment_date__lt=cutoff.date(),
            status='PENDING',
        )
        count = expired.count()
        expired.delete()
        return count
