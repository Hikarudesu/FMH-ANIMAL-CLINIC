"""Inventory expiry alert job utilities."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from inventory.models import Product
from notifications.models import Notification
from settings.utils import get_setting


User = get_user_model()


def run_inventory_expiry_alert_job(product_ids=None):
    """
    Create expiry warning notifications for products nearing expiration.

    Args:
        product_ids: Optional iterable of Product IDs to limit scope.

    Returns:
        dict with summary counts for logging/command output.
    """
    alerts_enabled = get_setting('inventory_enable_alerts', True)
    if not alerts_enabled:
        return {
            'alerts_enabled': False,
            'products_scanned': 0,
            'notifications_created': 0,
        }

    warning_days = int(get_setting('inventory_expiry_warning_days', 30) or 30)
    warning_days = max(1, warning_days)

    today = timezone.localdate()
    warning_until = today + timedelta(days=warning_days)

    products = Product.objects.filter(
        is_deleted=False,
        stock_quantity__gt=0,
        expiration_date__isnull=False,
        expiration_date__gte=today,
        expiration_date__lte=warning_until,
    ).select_related('branch')

    if product_ids:
        products = products.filter(id__in=product_ids)

    admins = User.objects.filter(is_staff=True)

    notifications_created = 0
    products_scanned = 0

    for product in products:
        products_scanned += 1
        days_left = (product.expiration_date - today).days
        if days_left == 0:
            lead_text = 'today'
        elif days_left == 1:
            lead_text = 'in 1 day'
        else:
            lead_text = f'in {days_left} days'

        title = 'Inventory Expiry Warning'
        message = (
            f"'{product.name}' (SKU: {product.sku or 'N/A'}) at "
            f"{product.branch.name if product.branch else 'Unassigned Branch'} "
            f"expires on {product.expiration_date:%Y-%m-%d} ({lead_text})."
        )

        # Notify admins
        for admin in admins:
            exists_today = Notification.objects.filter(
                user=admin,
                notification_type=Notification.NotificationType.INVENTORY_EXPIRY_ALERT,
                related_object_id=product.id,
                created_at__date=today,
            ).exists()

            if exists_today:
                continue

            Notification.objects.create(
                user=admin,
                title=title,
                message=message,
                notification_type=Notification.NotificationType.INVENTORY_EXPIRY_ALERT,
                module_context=Notification.ModuleContext.INVENTORY,
                related_object_id=product.id,
            )
            notifications_created += 1
        
        # Notify receptionists in the same branch
        if product.branch:
            receptionists = User.objects.filter(
                is_active=True,
                assigned_role__code='cashier',
                branch=product.branch,
            )
            
            for receptionist in receptionists:
                exists_today = Notification.objects.filter(
                    user=receptionist,
                    notification_type=Notification.NotificationType.INVENTORY_EXPIRY_ALERT,
                    related_object_id=product.id,
                    created_at__date=today,
                ).exists()

                if exists_today:
                    continue

                Notification.objects.create(
                    user=receptionist,
                    title=title,
                    message=message,
                    notification_type=Notification.NotificationType.INVENTORY_EXPIRY_ALERT,
                    module_context=Notification.ModuleContext.INVENTORY,
                    related_object_id=product.id,
                )
                notifications_created += 1
        
        # Also notify vet assistants in the same branch
        if product.branch:
            vet_assistants = User.objects.filter(
                is_active=True,
                assigned_role__code='assistant_veterinarian',
                branch=product.branch,
            )
            
            for vet_assistant in vet_assistants:
                exists_today = Notification.objects.filter(
                    user=vet_assistant,
                    notification_type=Notification.NotificationType.INVENTORY_EXPIRY_ALERT,
                    related_object_id=product.id,
                    created_at__date=today,
                ).exists()

                if exists_today:
                    continue

                Notification.objects.create(
                    user=vet_assistant,
                    title=title,
                    message=message,
                    notification_type=Notification.NotificationType.INVENTORY_EXPIRY_ALERT,
                    module_context=Notification.ModuleContext.INVENTORY,
                    related_object_id=product.id,
                )
                notifications_created += 1

    return {
        'alerts_enabled': True,
        'warning_days': warning_days,
        'products_scanned': products_scanned,
        'notifications_created': notifications_created,
    }
