"""Inventory expiry alert job utilities."""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from accounts.models import User
from accounts.rbac_constants import HierarchyLevels
from accounts.rbac_models import ModulePermission
from inventory.models import Product
from notifications.delivery import send_notification_email
from notifications.models import Notification
from notifications.utils import notify_module_users
from settings.utils import get_setting


def _expiry_email_recipients(branch):
    """Return active superadmins and full inventory managers for this branch."""
    manage_role_ids = ModulePermission.objects.filter(
        module__code='inventory',
        permission_type=ModulePermission.PermissionType.MANAGE,
    ).values_list('role_id', flat=True)
    users = User.objects.filter(is_active=True).exclude(email='').filter(
        Q(is_superuser=True)
        | Q(assigned_role__hierarchy_level__gte=HierarchyLevels.ADMIN)
        | Q(assigned_role_id__in=manage_role_ids)
    ).select_related('assigned_role').prefetch_related(
        'assigned_role__module_permissions__module'
    ).distinct()

    recipients = {}
    for user in users:
        if user.is_superuser:
            recipients.setdefault(user.email.strip().lower(), user.email.strip())
            continue

        role = user.assigned_role
        if role is None:
            continue

        if role.hierarchy_level >= HierarchyLevels.ADMIN:
            has_access = not user.branch_id or not branch or user.branch_id == branch.pk
        else:
            has_access = any(
                permission.module.code == 'inventory'
                and permission.permission_type == ModulePermission.PermissionType.MANAGE
                and (
                    not permission.restrict_to_branch
                    or user.branch_id == getattr(branch, 'pk', None)
                )
                for permission in role.module_permissions.all()
            )

        if has_access:
            email = user.email.strip()
            recipients.setdefault(email.lower(), email)

    return list(recipients.values())


def run_inventory_expiry_alert_job(product_ids=None):
    """
    Create expiry warning notifications for products nearing expiration.

    Args:
        product_ids: Optional iterable of Product IDs to limit scope.

    Returns:
        dict with summary counts for logging/command output.
    """
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

    notifications_created = 0
    products_scanned = 0
    emails_sent = 0

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

        email_already_sent_today = (
            days_left == warning_days
            and Notification.objects.filter(
                title=title,
                notification_type=Notification.NotificationType.INVENTORY_EXPIRY_ALERT,
                module_context=Notification.ModuleContext.INVENTORY,
                related_object_id=product.id,
                created_at__date=today,
            ).exists()
        )

        recipients = list(
            notify_module_users(
                module_code='inventory',
                branch=product.branch,
                title=title,
                message=message,
                notification_type=Notification.NotificationType.INVENTORY_EXPIRY_ALERT,
                module_context=Notification.ModuleContext.INVENTORY,
                related_object_id=product.id,
                dedupe_window_minutes=1440,
            ) or []
        )
        notifications_created += len(recipients)

        if days_left == warning_days and not email_already_sent_today:
            email_recipients = _expiry_email_recipients(product.branch)
            if email_recipients and send_notification_email(
                subject=(
                    f'[Inventory Expiry Alert] {product.name} '
                    f'expires in {days_left} days'
                ),
                message=(
                    f'The following inventory item expires in {days_left} days.\n\n'
                    f'Item: {product.name}\n'
                    f'SKU: {product.sku or "N/A"}\n'
                    f'Branch: {product.branch.name if product.branch else "Unassigned Branch"}\n'
                    f'Expiration date: {product.expiration_date:%Y-%m-%d}\n'
                    f'Current stock: {product.stock_quantity}\n'
                ),
                recipient_list=email_recipients,
                fail_silently=True,
            ):
                emails_sent += len(email_recipients)

    return {
        'alerts_enabled': True,
        'warning_days': warning_days,
        'products_scanned': products_scanned,
        'notifications_created': notifications_created,
        'emails_sent': emails_sent,
    }
