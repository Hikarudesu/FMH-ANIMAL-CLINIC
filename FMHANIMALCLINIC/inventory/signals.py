"""
Signal handlers for inventory app.
Automatically log activities when stock adjustments, reservations, and transfers occur.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from accounts.models import ActivityLog
from .models import StockAdjustment, Reservation, StockTransfer


@receiver(post_save, sender=StockAdjustment)
def log_stock_adjustment(sender, instance, created, **kwargs):
    """
    Log a stock adjustment activity.
    Triggered when a StockAdjustment is created.
    """
    if created:
        # Get a system user for logging (use superuser as fallback)
        from accounts.models import User
        system_user = User.objects.filter(is_superuser=True).first()

        # Determine action description based on adjustment type
        action_map = {
            'ADD': 'Added stock (Manual)',
            'REMOVE': 'Removed stock (Manual)',
            'SALE': 'Removed stock (Sale)',
            'TRANSFER_IN': 'Added stock (Transfer In)',
            'TRANSFER_OUT': 'Removed stock (Transfer Out)',
        }

        action = action_map.get(
            instance.adjustment_type,
            f'Stock adjusted ({instance.adjustment_type})'
        )

        details = (
            f"Product: {instance.product.name} | "
            f"Quantity: {instance.quantity} | "
            f"Reference: {instance.reference}"
        )
        if instance.reason:
            details += f" | Reason: {instance.reason}"

        ActivityLog.objects.create(
            user=system_user,
            action=action,
            category=ActivityLog.Category.STOCK,
            branch=instance.branch,
            details=details,
            timestamp=timezone.now()
        )


@receiver(post_save, sender=Reservation)
def log_reservation_activity(sender, instance, created, **kwargs):
    """
    Log a reservation activity.
    Triggered when a Reservation is created or its status changes.
    """
    status_action_map = {
        'PENDING': 'Reservation created',
        'RELEASED': 'Reservation released (completed)',
        'CANCELLED': 'Reservation cancelled',
    }

    action = status_action_map.get(instance.status, f'Reservation {instance.status}')

    details = (
        f"Product: {instance.product.name} | "
        f"Quantity: {instance.quantity} | "
        f"User: {instance.user.get_full_name() or instance.user.username}"
    )

    ActivityLog.objects.create(
        user=instance.user,
        action=action,
        category=ActivityLog.Category.STOCK,
        branch=instance.product.branch,
        details=details,
        timestamp=timezone.now()
    )


@receiver(post_save, sender=StockTransfer)
def log_stock_transfer(sender, instance, created, **kwargs):
    """
    Log a stock transfer activity.
    """
    if created:
        action = f'Stock transfer requested: {instance.quantity}x {instance.source_product.name}'
    else:
        action = f'Stock transfer {instance.status.lower()}: {instance.quantity}x {instance.source_product.name}'

    details = (
        f"From: {instance.source_product.branch.name} | "
        f"To: {instance.destination_branch.name} | "
        f"Product: {instance.source_product.name} | "
        f"Quantity: {instance.quantity}"
    )

    ActivityLog.objects.create(
        user=instance.requested_by if created else (instance.processed_by or instance.requested_by),
        action=action,
        category=ActivityLog.Category.STOCK,
        branch=instance.destination_branch,
        details=details,
        timestamp=timezone.now()
    )
