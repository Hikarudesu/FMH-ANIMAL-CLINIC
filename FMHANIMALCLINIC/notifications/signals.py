from django.db.models.signals import post_save
from django.db.models import Q
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from .models import Notification
from .utils import (
    create_notification,
    notify_module_users,
    notify_inquiry_received,
    notify_staff_appointment_status_change,
)
from appointments.models import Appointment
from inventory.models import Product, StockAdjustment
from inventory.expiry_alerts import run_inventory_expiry_alert_job
from settings.utils import get_setting
from inquiries.models import Inquiry


User = get_user_model()


def get_admin_users():
    """Helper function to get all admin users."""
    return User.objects.filter(is_active=True).filter(
        Q(is_superuser=True) | Q(assigned_role__code='executive_officer')
    )


@receiver(post_save, sender=Appointment)
def create_appointment_notification(sender, instance, created, **kwargs):
    """
    Creates a notification when a new appointment is created.
    Notify every appointment-enabled staff member in the appointment branch,
    including all veterinarians for an any-available-vet appointment.
    """
    if created:
        notify_staff_appointment_status_change(
            instance,
            instance.status,
        )


@receiver(post_save, sender=Inquiry)
def create_inquiry_notification(sender, instance, created, **kwargs):
    """Notify staff whenever a new inquiry is saved through any code path."""
    if created:
        notify_inquiry_received(instance)


@receiver(post_save, sender=Product)
def create_low_inventory_notification(sender, instance, **kwargs):
    """
    Creates low/critical inventory notifications using configured system thresholds.
    Alerts are controlled by inventory settings in the System Settings page.
    Notifies admins, receptionists, and vet assistants (who have inventory module access).
    """
    alerts_enabled = get_setting('inventory_enable_alerts', True)
    if not alerts_enabled:
        return

    low_threshold = int(get_setting('inventory_low_stock_threshold', 10) or 10)
    critical_threshold = int(get_setting('inventory_critical_threshold', 5) or 5)

    if instance.stock_quantity > low_threshold:
        return

    is_critical = instance.stock_quantity <= critical_threshold
    title = "Critical Inventory Alert" if is_critical else "Low Inventory Alert"
    level_text = "critical" if is_critical else "low"
    message = (
        f"Stock for '{instance.name}' is {level_text} "
        f"({instance.stock_quantity} remaining). "
        f"Thresholds: critical <= {critical_threshold}, low <= {low_threshold}."
    )

    notify_module_users(
        module_code='inventory',
        branch=instance.branch,
        title=title,
        message=message,
        notification_type=Notification.NotificationType.LOW_INVENTORY,
        module_context=Notification.ModuleContext.INVENTORY,
        related_object_id=instance.id,
    )



@receiver(post_save, sender=Product)
def create_inventory_expiry_notification(sender, instance, **kwargs):
    """Generate expiry warning notifications when a product is created/updated."""
    if not instance.expiration_date:
        return

    run_inventory_expiry_alert_job(product_ids=[instance.id])


@receiver(post_save, sender=StockAdjustment)
def create_inventory_restock_notification(sender, instance, created, **kwargs):
    """
    Creates a notification for admin users, receptionists, and vet assistants when a product is restocked.
    All these roles have inventory module access.
    """
    if created and instance.adjustment_type == 'ADD' and instance.quantity > 0:
        message = f"{instance.quantity} units of '{instance.product.name}' have been received."
        
        notify_module_users(
            module_code='inventory',
            branch=instance.product.branch,
            title="Inventory Restocked",
            message=message,
            notification_type=Notification.NotificationType.INVENTORY_RESTOCK,
            module_context=Notification.ModuleContext.INVENTORY,
            related_object_id=instance.product.id,
        )
