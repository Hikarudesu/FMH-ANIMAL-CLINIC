"""
Signal handlers for inventory app.
Automatically log activities when stock adjustments, reservations, and transfers occur.
Also creates notifications for reservation state changes and other inventory events.
"""
from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver

from accounts.activity_context import get_current_actor
from accounts.models import ActivityLog, log_activity
from .models import StockAdjustment, Reservation, StockTransfer

# Store to track previous status in pre_save
_reservation_previous_status = {}


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

        log_activity(
            user=get_current_actor() or system_user,
            action=action,
            category=ActivityLog.Category.STOCK,
            action_type=ActivityLog.ActionType.CREATE,
            branch=instance.branch,
            details=details,
            object_type='StockAdjustment',
            object_id=instance.pk,
        )


@receiver(pre_save, sender=Reservation)
def track_reservation_status_change(sender, instance, **kwargs):
    """
    Track previous status before save to detect status changes.
    Stores in module-level dict for use in post_save handler.
    """
    if instance.pk:  # Only if it's an update, not a create
        try:
            old_instance = Reservation.objects.get(pk=instance.pk)
            _reservation_previous_status[instance.pk] = old_instance.status
        except Reservation.DoesNotExist:
            _reservation_previous_status[instance.pk] = None
    else:
        _reservation_previous_status[instance.pk] = None


@receiver(post_save, sender=Reservation)
def handle_reservation_notifications_and_logging(sender, instance, created, **kwargs):
    """
    Create notifications and log activities for reservations.
    Triggered when a Reservation is created or its status changes.
    """
    from notifications.utils import (
        notify_reservation_approved,
        notify_reservation_ready,
        notify_reservation_rejected,
    )
    
    # Get previous status for detecting changes
    previous_status = _reservation_previous_status.pop(instance.pk, None)
    
    # Log the activity
    status_action_map = {
        'Pending': 'Reservation created',
        'Released': 'Reservation released (completed)',
        'Cancelled': 'Reservation cancelled',
    }

    action = status_action_map.get(instance.status, f'Reservation {instance.status}')

    details = (
        f"Product: {instance.product.name} | "
        f"Quantity: {instance.quantity} | "
        f"User: {instance.user.get_full_name() or instance.user.username}"
    )

    log_activity(
        user=get_current_actor() or instance.user,
        action=action,
        category=ActivityLog.Category.STOCK,
        action_type=(
            ActivityLog.ActionType.CREATE if created
            else ActivityLog.ActionType.UPDATE
        ),
        branch=instance.product.branch,
        details=details,
        object_type='Reservation',
        object_id=instance.pk,
    )
    
    # Create notifications based on status changes
    if created:
        # New reservation created - initially in PENDING status
        pass  # No notification needed for initial creation
    elif previous_status and previous_status != instance.status:
        # Status changed - send appropriate notification
        if instance.status == 'Released':
            # Changed to RELEASED = READY for pickup
            notify_reservation_ready(instance)
        elif instance.status == 'Cancelled':
            # Changed to CANCELLED = REJECTED
            notify_reservation_rejected(instance)


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

    log_activity(
        user=(
            get_current_actor()
            or (instance.requested_by if created else (instance.processed_by or instance.requested_by))
        ),
        action=action,
        category=ActivityLog.Category.STOCK,
        action_type=(
            ActivityLog.ActionType.CREATE if created
            else ActivityLog.ActionType.UPDATE
        ),
        branch=instance.destination_branch,
        details=details,
        object_type='StockTransfer',
        object_id=instance.pk,
    )


@receiver(pre_delete, sender=Reservation)
def log_reservation_delete(sender, instance, **kwargs):
    """Log reservation deletion before related records are removed."""
    actor = get_current_actor() or instance.user
    if not actor:
        return
    log_activity(
        user=actor,
        action=f'Reservation deleted: {instance.pk}',
        category=ActivityLog.Category.STOCK,
        action_type=ActivityLog.ActionType.DELETE,
        branch=instance.product.branch,
        details=f'Product: {instance.product.name} | Quantity: {instance.quantity}',
        object_type='Reservation',
        object_id=instance.pk,
    )


@receiver(pre_delete, sender=StockTransfer)
def log_stock_transfer_delete(sender, instance, **kwargs):
    """Log stock transfer deletion before related records are removed."""
    actor = get_current_actor() or instance.requested_by
    if not actor:
        return
    log_activity(
        user=actor,
        action=f'Stock transfer deleted: {instance.pk}',
        category=ActivityLog.Category.STOCK,
        action_type=ActivityLog.ActionType.DELETE,
        branch=instance.destination_branch,
        details=f'Product: {instance.source_product.name} | Quantity: {instance.quantity}',
        object_type='StockTransfer',
        object_id=instance.pk,
    )
