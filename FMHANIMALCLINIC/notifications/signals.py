from django.db.models.signals import post_save
from django.db.models import Q
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from .models import Notification
from .utils import create_notification, notify_role_users
from appointments.models import Appointment
from inventory.models import Product, StockAdjustment
from inventory.expiry_alerts import run_inventory_expiry_alert_job
from settings.utils import get_setting


User = get_user_model()


def get_admin_users():
    """Helper function to get all admin users."""
    return User.objects.filter(is_active=True).filter(
        Q(is_superuser=True) | Q(assigned_role__code='branch_admin')
    )


@receiver(post_save, sender=Appointment)
def create_appointment_notification(sender, instance, created, **kwargs):
    """
    Creates a notification when a new appointment is created.
    Notifies receptionists and vet assistants (who monitor appointments).
    """
    if created:
        appointment_msg = (
            f"A new appointment for {instance.pet_name} was booked for "
            f"{instance.appointment_date} at {instance.appointment_time.strftime('%I:%M %p')}."
        )
        
        # Notify receptionists
        notify_role_users(
            role_code='receptionist',
            branch=instance.branch,
            title='New Appointment Booking',
            message=appointment_msg,
            notification_type=Notification.NotificationType.APPOINTMENT,
            module_context=Notification.ModuleContext.APPOINTMENTS,
            related_object_id=instance.id,
        )
        
        # Notify vet assistants (who have appointments module access)
        notify_role_users(
            role_code='vet_assistant',
            branch=instance.branch,
            title='New Appointment Booking',
            message=appointment_msg,
            notification_type=Notification.NotificationType.APPOINTMENT,
            module_context=Notification.ModuleContext.APPOINTMENTS,
            related_object_id=instance.id,
        )
        
        # Notify veterinarians (who manage appointments)
        notify_role_users(
            role_code='veterinarian',
            branch=instance.branch,
            title='New Appointment Booking',
            message=appointment_msg,
            notification_type=Notification.NotificationType.APPOINTMENT,
            module_context=Notification.ModuleContext.APPOINTMENTS,
            related_object_id=instance.id,
        )


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

    # Track users already notified to avoid duplicates
    notified_user_ids = set()

    # Notify admin users
    for admin in get_admin_users():
        existing = Notification.objects.filter(
            user=admin,
            notification_type=Notification.NotificationType.LOW_INVENTORY,
            related_object_id=instance.id,
            is_read=False
        ).exists()

        if not existing:
            create_notification(
                user=admin,
                title=title,
                message=message,
                notification_type=Notification.NotificationType.LOW_INVENTORY,
                module_context=Notification.ModuleContext.INVENTORY,
                related_object_id=instance.id,
            )
            notified_user_ids.add(admin.id)
    
    # Notify receptionists in the same branch
    from accounts.models import User
    receptionists = User.objects.filter(
        is_active=True,
        assigned_role__code='receptionist',
        branch=instance.branch,
    ).exclude(id__in=notified_user_ids)
    
    for receptionist in receptionists:
        existing = Notification.objects.filter(
            user=receptionist,
            notification_type=Notification.NotificationType.LOW_INVENTORY,
            related_object_id=instance.id,
            is_read=False
        ).exists()

        if not existing:
            create_notification(
                user=receptionist,
                title=title,
                message=message,
                notification_type=Notification.NotificationType.LOW_INVENTORY,
                module_context=Notification.ModuleContext.INVENTORY,
                related_object_id=instance.id,
            )
            notified_user_ids.add(receptionist.id)
    
    # Also notify vet assistants in the same branch
    vet_assistants = User.objects.filter(
        is_active=True,
        assigned_role__code='vet_assistant',
        branch=instance.branch,
    ).exclude(id__in=notified_user_ids)
    
    for vet_assistant in vet_assistants:
        existing = Notification.objects.filter(
            user=vet_assistant,
            notification_type=Notification.NotificationType.LOW_INVENTORY,
            related_object_id=instance.id,
            is_read=False
        ).exists()

        if not existing:
            create_notification(
                user=vet_assistant,
                title=title,
                message=message,
                notification_type=Notification.NotificationType.LOW_INVENTORY,
                module_context=Notification.ModuleContext.INVENTORY,
                related_object_id=instance.id,
            )
            notified_user_ids.add(vet_assistant.id)



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
        
        # Track users already notified to avoid duplicates
        notified_user_ids = set()
        
        # Notify admin users
        for admin in get_admin_users():
            create_notification(
                user=admin,
                title="Inventory Restocked",
                message=message,
                notification_type=Notification.NotificationType.INVENTORY_RESTOCK,
                module_context=Notification.ModuleContext.INVENTORY,
                related_object_id=instance.product.id,
            )
            notified_user_ids.add(admin.id)
        
        # Notify receptionists in the same branch
        from accounts.models import User
        receptionists = User.objects.filter(
            is_active=True,
            assigned_role__code='receptionist',
            branch=instance.product.branch,
        ).exclude(id__in=notified_user_ids)
        
        for receptionist in receptionists:
            create_notification(
                user=receptionist,
                title="Inventory Restocked",
                message=message,
                notification_type=Notification.NotificationType.INVENTORY_RESTOCK,
                module_context=Notification.ModuleContext.INVENTORY,
                related_object_id=instance.product.id,
            )
            notified_user_ids.add(receptionist.id)
        
        # Also notify vet assistants in the same branch
        vet_assistants = User.objects.filter(
            is_active=True,
            assigned_role__code='vet_assistant',
            branch=instance.product.branch,
        ).exclude(id__in=notified_user_ids)
        
        for vet_assistant in vet_assistants:
            create_notification(
                user=vet_assistant,
                title="Inventory Restocked",
                message=message,
                notification_type=Notification.NotificationType.INVENTORY_RESTOCK,
                module_context=Notification.ModuleContext.INVENTORY,
                related_object_id=instance.product.id,
            )
            notified_user_ids.add(vet_assistant.id)

        # Also notify veterinarians in the same branch
        veterinarians = User.objects.filter(
            is_active=True,
            assigned_role__code='veterinarian',
            branch=instance.product.branch,
        ).exclude(id__in=notified_user_ids)

        for veterinarian in veterinarians:
            create_notification(
                user=veterinarian,
                title="Inventory Restocked",
                message=message,
                notification_type=Notification.NotificationType.INVENTORY_RESTOCK,
                module_context=Notification.ModuleContext.INVENTORY,
                related_object_id=instance.product.id,
            )
            notified_user_ids.add(veterinarian.id)

