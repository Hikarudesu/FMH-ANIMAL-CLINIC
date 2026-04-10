"""
Models for the inventory application.
"""
import uuid

from django.db import models
from django.conf import settings
from django.utils import timezone
from branches.models import Branch
from utils.models import SoftDeleteModel


class Product(SoftDeleteModel):
    """Represents a product or medication in the clinic's inventory."""

    ITEM_TYPE_CHOICES = [
        ('Product', 'Product'),
        ('Medication', 'Medication'),
        ('Accessories', 'Accessories'),
        ('Medical Supplies', 'Medical Supplies'),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    item_type = models.CharField(
        max_length=20, choices=ITEM_TYPE_CHOICES, default='Product')

    # Identification
    sku = models.CharField(
        max_length=100, blank=True,
        help_text="Stock Keeping Unit (auto-generated if blank)")
    barcode = models.CharField(
        max_length=100, blank=True,
        help_text="Barcode / UPC number")
    manufacturer = models.CharField(max_length=200, blank=True)

    # Financial fields
    unit_cost = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    branch = models.ForeignKey(
        Branch, on_delete=models.CASCADE, related_name='products')
    is_available = models.BooleanField(default=True)
    stock_quantity = models.PositiveIntegerField(default=0)
    min_stock_level = models.PositiveIntegerField(default=5)
    is_consumable = models.BooleanField(
        default=False,
        help_text='True for single-use / consumable items (medicines, medical supplies)'
    )

    # Safety
    expiration_date = models.DateField(
        null=True, blank=True,
        help_text="For medications or perishable items")

    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Meta options for the Product model."""
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['branch', 'item_type']),
            models.Index(fields=['stock_quantity']),
            models.Index(fields=['is_available']),
            models.Index(fields=['branch', 'created_at']),
        ]

    def __str__(self):
        return str(self.name)

    @property
    def status(self):
        """Returns the current stock status."""
        if self.stock_quantity <= 0:
            return 'Out of Stock'
        if self.stock_quantity <= self.min_stock_level:
            return 'Low Stock'
        return 'In Stock'

    @property
    def inventory_value(self):
        """Total valuation of this item in stock based on cost."""
        return self.stock_quantity * self.unit_cost

    @property
    def profit_margin(self):
        """Profit margin percentage per unit."""
        if self.price and self.price > 0:
            return round(
                ((self.price - self.unit_cost) / self.price) * 100, 1
            )
        return 0

    def save(self, *args, **kwargs):
        """Override save to auto-generate SKU and verify availability."""
        if self.stock_quantity == 0:
            self.is_available = False
        else:
            self.is_available = True

        # Auto-generate SKU if blank
        if not self.sku:
            prefix_map = {
                'Medication': 'MED',
                'Accessories': 'ACC',
                'Medical Supplies': 'MSP',
            }
            prefix = prefix_map.get(self.item_type, 'PRD')
            self.sku = f"{prefix}-{str(uuid.uuid4())[:6].upper()}"

        super().save(*args, **kwargs)


class StockAdjustment(models.Model):
    """
    Tracks history of stock changes.
    
    User-facing types (for manual adjustments):
        - ADD: Manual addition/restock
        - REMOVE: Manual deduction/adjustment
    
    System-only types (for internal signals - not shown in forms):
        - SALE: Automatic deduction from POS transactions
        - TRANSFER_IN: Stock received from branch transfer
        - TRANSFER_OUT: Stock sent to another branch
    """

    # Simplified adjustment types for user-facing operations
    ADJUSTMENT_TYPES = [
        ('ADD', 'Add Stock (Restock / Manual Addition)'),
        ('REMOVE', 'Remove Stock (Adjustment / Manual Deduction)'),
    ]

    # System-only types (used internally by signals, not shown in forms)
    SYSTEM_ADJUSTMENT_TYPES = [
        ('SALE', 'Remove Stock (Sale)'),
        ('TRANSFER_IN', 'Add Stock (Transfer Received)'),
        ('TRANSFER_OUT', 'Remove Stock (Transfer Sent)'),
    ]

    # Combined choices for the model field (allows both user and system types)
    ALL_ADJUSTMENT_TYPES = ADJUSTMENT_TYPES + SYSTEM_ADJUSTMENT_TYPES

    # Types that result in stock deduction
    DEDUCTION_TYPES = ['REMOVE', 'SALE', 'TRANSFER_OUT']

    branch = models.ForeignKey(
        Branch, on_delete=models.CASCADE, related_name='stock_adjustments')
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='stock_adjustments')

    adjustment_type = models.CharField(
        max_length=20, choices=ALL_ADJUSTMENT_TYPES, default='ADD')
    reference = models.CharField(
        max_length=50, blank=True, default='',
        help_text="Optional: Receipt #, Invoice ID, or leave blank")
    date = models.DateField()

    quantity = models.IntegerField(
        help_text="Number of items to add or remove.")
    cost_per_unit = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00,
        blank=True, help_text="Optional: Cost per unit for restocks")

    reason = models.CharField(
        max_length=255, default='Manual adjustment',
        help_text="Reason for this adjustment (required)")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Meta options for StockAdjustment."""
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.product.name} ({self.get_adjustment_type_display()}) - {self.quantity}"

    def save(self, *args, **kwargs):
        from django.db import transaction
        from django.db.models import F

        is_new = self.pk is None

        # Auto-generate reference if blank
        if not self.reference:
            self.reference = f"ADJ-{timezone.now().strftime('%Y%m%d%H%M%S')}"

        # Enforce negative sign for deduction types before saving
        if is_new and self.adjustment_type in self.DEDUCTION_TYPES:
            if self.quantity > 0:
                self.quantity = -self.quantity

        super().save(*args, **kwargs)

        if is_new:
            # Use atomic update with F() expression to avoid race conditions
            with transaction.atomic():
                Product.objects.filter(pk=self.product.pk).update(
                    stock_quantity=F('stock_quantity') + self.quantity
                )
                # Ensure stock doesn't go below 0
                Product.objects.filter(pk=self.product.pk, stock_quantity__lt=0).update(
                    stock_quantity=0
                )


class Reservation(models.Model):
    """A product reservation made by a user from the digital catalog."""

    class Status(models.TextChoices):
        """Status choices for a Reservation."""
        PENDING = 'Pending', 'Pending'
        RELEASED = 'Released', 'Released'
        CANCELLED = 'Cancelled', 'Cancelled'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reservations',
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='reservations')
    quantity = models.PositiveIntegerField(default=1)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    notes = models.TextField(blank=True)
    pickup_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Meta options for Reservation."""
        ordering = ['-created_at']

    def __str__(self):
        return (
            f"Reservation #{self.pk} — {self.product.name} "
            f"x{self.quantity} ({self.status})"
        )


class StockTransfer(models.Model):
    """Tracks inventory transfers between branches."""

    class Status(models.TextChoices):
        """Status choices for a StockTransfer."""
        PENDING = 'Pending', 'Pending'
        APPROVED = 'Approved', 'Approved'
        REJECTED = 'Rejected', 'Rejected'
        COMPLETED = 'Completed', 'Completed'

    source_product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='outgoing_transfers')
    destination_branch = models.ForeignKey(
        Branch, on_delete=models.CASCADE, related_name='incoming_transfers')

    quantity = models.PositiveIntegerField(default=1)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING)

    notes = models.TextField(
        blank=True, help_text="Reason for transfer or special instructions")

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='requested_transfers'
    )
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='processed_transfers'
    )

    class Meta:
        """Meta options for StockTransfer."""
        ordering = ['-created_at']

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return (
            f"Transfer {self.quantity}x {self.source_product.name} "
            f"to {self.destination_branch.name}"
        )

    def complete_transfer(self, user):
        """Executes the transfer of stock if status changes to COMPLETED."""
        if self.status not in (self.Status.PENDING, self.Status.APPROVED):
            raise ValueError(
                "Transfer must be pending or approved to complete.")

        # Validate sufficient stock
        # pylint: disable=no-member
        if self.source_product.stock_quantity < self.quantity:
            raise ValueError("Insufficient stock in source branch.")

        from django.db import transaction
        with transaction.atomic():
            # Deduct from source via StockAdjustment (its save() updates stock_quantity)
            StockAdjustment.objects.create(
                branch=self.source_product.branch,
                product=self.source_product,
                adjustment_type='TRANSFER_OUT',
                reference=f"TRF-OUT-{self.pk}",
                date=timezone.now().date(),
                quantity=self.quantity,
                reason=f"Transfer to {self.destination_branch.name}",
                cost_per_unit=self.source_product.unit_cost
            )

            # Create or find destination product
            dest_product, _created = Product.objects.get_or_create(
                sku=self.source_product.sku,
                branch=self.destination_branch,
                defaults={
                    'name': self.source_product.name,
                    'description': self.source_product.description,
                    'item_type': self.source_product.item_type,
                    'barcode': self.source_product.barcode,
                    'manufacturer': self.source_product.manufacturer,
                    'unit_cost': self.source_product.unit_cost,
                    'price': self.source_product.price,
                    'min_stock_level': self.source_product.min_stock_level,
                    'expiration_date': self.source_product.expiration_date,
                }
            )

            # Add to destination via StockAdjustment (its save() updates stock_quantity)
            StockAdjustment.objects.create(
                branch=self.destination_branch,
                product=dest_product,
                adjustment_type='TRANSFER_IN',
                reference=f"TRF-IN-{self.pk}",
                date=timezone.now().date(),
                quantity=self.quantity,
                reason=f"Transfer from {self.source_product.branch.name}",
                cost_per_unit=dest_product.unit_cost
            )

            self.status = self.Status.COMPLETED
            self.processed_by = user
            self.save(update_fields=['status', 'processed_by', 'updated_at'])
