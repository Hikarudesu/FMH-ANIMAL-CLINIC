"""Billing app models."""

from django.db import models
from branches.models import Branch
from utils.models import SoftDeleteModel


class Service(SoftDeleteModel):
    """Represents a clinic service (consultations, procedures, grooming, etc.)."""

    name = models.CharField(max_length=200)
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL,
                               null=True, blank=True, related_name='services')
    category = models.CharField(max_length=100, blank=True)
    tax_rate = models.CharField(max_length=50, blank=True)
    duration = models.IntegerField(default=0, help_text="Duration in minutes")

    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    content = models.TextField(
        blank=True, help_text="Manage content associated with this service.")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Meta options."""
        ordering = ['-created_at']

    def __str__(self):
        return str(self.name)


class CustomerStatement(models.Model):
    """
    Stores Statement of Account created by admin staff.
    Can be released to customers for viewing in their portal.
    """

    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('RELEASED', 'Released to Customer'),
        ('SENT', 'Sent via Email'),
    ]

    # Statement Information
    statement_number = models.CharField(max_length=20, unique=True, blank=True)
    patient_name = models.CharField(max_length=100, help_text="Pet name")
    owner_name = models.CharField(max_length=200, help_text="Pet owner name")
    date = models.DateField(help_text="Statement date")

    # Link to customer (optional - can be walk-in)
    customer = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        limit_choices_to={'role': 'PET_OWNER'},
        related_name='statements',
        help_text="Link to registered customer account"
    )
    sale = models.ForeignKey(
        'pos.Sale',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customer_statements',
        help_text='Linked POS sale that generated this statement.',
    )

    # Service Amounts
    consultation_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    consultation_description = models.TextField(blank=True, help_text="Description of consultation services")
    treatment = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    treatment_description = models.TextField(blank=True, help_text="Description of treatment services")
    boarding = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    boarding_description = models.TextField(blank=True, help_text="Description of boarding services")
    vaccination = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    vaccination_description = models.TextField(blank=True, help_text="Description of vaccination services")
    surgery = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    surgery_description = models.TextField(blank=True, help_text="Description of surgical services")
    laboratory = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    laboratory_description = models.TextField(blank=True, help_text="Description of laboratory services")
    grooming = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    grooming_description = models.TextField(blank=True, help_text="Description of grooming services")
    others = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    others_description = models.TextField(blank=True, help_text="Description of other services")

    # Totals
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    deposit = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    # Status and Metadata
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='DRAFT')
    notes = models.TextField(blank=True, help_text="Internal notes")

    # Tracking
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='created_statements'
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        null=True, blank=True
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    released_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Customer Statement'
        verbose_name_plural = 'Customer Statements'

    def __str__(self):
        return f"{self.statement_number} - {self.patient_name} ({self.owner_name})"

    def save(self, *args, **kwargs):
        # Auto-generate statement number
        if not self.statement_number:
            from django.utils import timezone
            date_str = timezone.now().strftime('%Y%m%d')
            # Get next sequence number for the day
            last_statement = CustomerStatement.objects.filter(
                statement_number__startswith=f"SOA{date_str}"
            ).order_by('statement_number').last()

            if last_statement:
                last_seq = int(last_statement.statement_number[-3:])
                seq = f"{last_seq + 1:03d}"
            else:
                seq = "001"

            self.statement_number = f"SOA{date_str}{seq}"

        # Auto-calculate balance
        self.balance = self.total_amount - self.deposit

        super().save(*args, **kwargs)

    def release_to_customer(self, user=None):
        """Release this statement to customer for viewing."""
        from django.utils import timezone

        if self.status != 'DRAFT':
            raise ValueError("Only draft statements can be released")

        self.status = 'RELEASED'
        self.released_at = timezone.now()
        self.save()

    def is_released(self):
        """Check if statement has been released to customer."""
        return self.status in ['RELEASED', 'SENT']
