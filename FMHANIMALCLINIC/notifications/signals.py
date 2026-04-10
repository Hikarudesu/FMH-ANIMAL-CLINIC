from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from .models import Notification
from appointments.models import Appointment
from inventory.models import Product, StockAdjustment


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
    Creates a notification for admin users when a product's stock is low (<= 10).
    Ideally, this should check if it just crossed the threshold to avoid spamming,
    but for simplicity, we'll check if it's currently low and a notification hasn't
    been created very recently.
    """
    # A simple approach: just check the quantity. 
    # To prevent spam, we could check if a notification for this product ID 
    # and LOW_INVENTORY type was created today, but we will keep it simple here.
    if instance.stock_quantity <= 10:
        # Prevent creating multiple notifications for every save by checking if one exists and is unread
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
                    title="Low Inventory Alert",
                    message=f"Stock for '{instance.name}' is running low ({instance.stock_quantity} remaining).",
                    notification_type=Notification.NotificationType.LOW_INVENTORY,
                    module_context=Notification.ModuleContext.INVENTORY,
                    related_object_id=instance.id,
                )


@receiver(post_save, sender=StockAdjustment)
def create_inventory_restock_notification(sender, instance, created, **kwargs):
    """
    Creates a notification for admin users when a product is restocked (Purchase).
    """
    if created and instance.adjustment_type == 'Purchase' and instance.quantity > 0:
        for admin in get_admin_users():
            Notification.objects.create(
                user=admin,
                title="Inventory Restocked",
                message=f"{instance.quantity} units of '{instance.product.name}' have been received.",
                notification_type=Notification.NotificationType.INVENTORY_RESTOCK,
                module_context=Notification.ModuleContext.INVENTORY,
                related_object_id=instance.product.id,
            )
