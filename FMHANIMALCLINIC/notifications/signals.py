from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from .models import Notification
from appointments.models import Appointment
from inventory.models import Product, StockAdjustment
from inventory.expiry_alerts import run_inventory_expiry_alert_job
from settings.utils import get_setting


User = get_user_model()


def get_admin_users():
    """Helper function to get all admin users."""
    # Assuming admins are superusers or staff, or have a specific role based on the User model
    # For now, we will query users where is_staff=True or is_superuser=True
    return User.objects.filter(is_staff=True)


@receiver(post_save, sender=Appointment)
def create_appointment_notification(sender, instance, created, **kwargs):
    """
    Creates a notification for admin users when a new appointment is created.
    """
    if created:
        for admin in get_admin_users():
            Notification.objects.create(
                user=admin,
                title="New Appointment",
                message=f"A new appointment has been scheduled for {instance.pet_name} on {instance.appointment_date}.",
                notification_type=Notification.NotificationType.APPOINTMENT,
                module_context=Notification.ModuleContext.APPOINTMENTS,
                related_object_id=instance.id,
            )


@receiver(post_save, sender=Product)
def create_low_inventory_notification(sender, instance, **kwargs):
    """
    Creates low/critical inventory notifications using configured system thresholds.
    Alerts are controlled by inventory settings in the System Settings page.
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

    for admin in get_admin_users():
        existing = Notification.objects.filter(
            user=admin,
            notification_type=Notification.NotificationType.LOW_INVENTORY,
            related_object_id=instance.id,
            is_read=False
        ).exists()

        if not existing:
            Notification.objects.create(
                user=admin,
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
    Creates a notification for admin users when a product is restocked.
    """
    if created and instance.adjustment_type == 'ADD' and instance.quantity > 0:
        for admin in get_admin_users():
            Notification.objects.create(
                user=admin,
                title="Inventory Restocked",
                message=f"{instance.quantity} units of '{instance.product.name}' have been received.",
                notification_type=Notification.NotificationType.INVENTORY_RESTOCK,
                module_context=Notification.ModuleContext.INVENTORY,
                related_object_id=instance.product.id,
            )
