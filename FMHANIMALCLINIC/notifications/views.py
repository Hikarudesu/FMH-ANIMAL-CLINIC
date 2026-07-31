from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Q

from .models import Notification
from accounts.decorators import module_permission_required


# ════════════════════════════════════════════════════════════════════════════
# NOTIFICATION TYPE TO MODULE CONTEXT MAPPING
# ════════════════════════════════════════════════════════════════════════════

def get_notification_type_to_module_mapping():
    """
    Map notification types to their module contexts.
    This ensures users only see notification types relevant to their accessible modules.
    
    IMPORTANT NOTES:
    - STOCK_TRANSFER_* notifications use module_context=INVENTORY but are only sent to superadmins
    - RESERVATION_* notifications are for the reservations module
    """
    return {
        # Appointments module
        Notification.NotificationType.FOLLOW_UP: Notification.ModuleContext.APPOINTMENTS,
        Notification.NotificationType.APPOINTMENT: Notification.ModuleContext.APPOINTMENTS,
        Notification.NotificationType.APPOINTMENT_CONFIRMED: Notification.ModuleContext.APPOINTMENTS,
        Notification.NotificationType.APPOINTMENT_CANCELLED: Notification.ModuleContext.APPOINTMENTS,
        Notification.NotificationType.APPOINTMENT_RESCHEDULED: Notification.ModuleContext.APPOINTMENTS,
        Notification.NotificationType.APPOINTMENT_REMINDER_1: Notification.ModuleContext.APPOINTMENTS,
        Notification.NotificationType.APPOINTMENT_REMINDER_2: Notification.ModuleContext.APPOINTMENTS,
        Notification.NotificationType.FOLLOW_UP_OVERDUE: Notification.ModuleContext.APPOINTMENTS,
        
        # Medical Records module
        Notification.NotificationType.MEDICAL_RECORD_UPDATE: Notification.ModuleContext.MEDICAL_RECORDS,
        
        # Inventory module - low stock and expiry alerts for staff with inventory access
        Notification.NotificationType.INVENTORY_RESTOCK: Notification.ModuleContext.INVENTORY,
        Notification.NotificationType.LOW_INVENTORY: Notification.ModuleContext.INVENTORY,
        Notification.NotificationType.INVENTORY_EXPIRY_ALERT: Notification.ModuleContext.INVENTORY,
        Notification.NotificationType.LOW_STOCK_ALERT: Notification.ModuleContext.INVENTORY,
        # Product reservations and reservation status notifications are created
        # with module_context=Notification.ModuleContext.INVENTORY, so map them
        # to the INVENTORY module here to keep filters consistent.
        Notification.NotificationType.PRODUCT_RESERVATION: Notification.ModuleContext.INVENTORY,
        
        # Stock Transfer notifications are only sent to superadmins, mapped to non-existent module
        # to prevent them appearing in staff notification filters
        Notification.NotificationType.STOCK_TRANSFER_REQUESTED: '_superadmin_only',
        Notification.NotificationType.STOCK_TRANSFER_APPROVED: '_superadmin_only',
        Notification.NotificationType.STOCK_TRANSFER_REJECTED: '_superadmin_only',
        Notification.NotificationType.STOCK_TRANSFER_COMPLETED: '_superadmin_only',
        
        # Reservations module - now available for receptionists
        Notification.NotificationType.RESERVATION_APPROVED: Notification.ModuleContext.INVENTORY,
        Notification.NotificationType.RESERVATION_REJECTED: Notification.ModuleContext.INVENTORY,
        Notification.NotificationType.RESERVATION_READY: Notification.ModuleContext.INVENTORY,
        
        # SOA (Statement of Account) module
        Notification.NotificationType.STATEMENT_RELEASED: Notification.ModuleContext.SOA,
        
        # Inquiries module - only for superadmins/branch admins
        Notification.NotificationType.INQUIRY_NEW: Notification.ModuleContext.INQUIRIES,
        Notification.NotificationType.INQUIRY_RESPONDED: Notification.ModuleContext.INQUIRIES,
        Notification.NotificationType.INQUIRY_ARCHIVED: Notification.ModuleContext.INQUIRIES,
        
        # Payroll module - only for superadmins/branch admins
        Notification.NotificationType.PAYROLL_GENERATED: Notification.ModuleContext.PAYROLL,
        Notification.NotificationType.PAYROLL_RELEASED: Notification.ModuleContext.PAYROLL,
        
        # General - always allowed
        Notification.NotificationType.GENERAL: Notification.ModuleContext.GENERAL,
    }


def _get_allowed_notification_types_from_modules(module_codes, *, include_superadmin_only=False):
    """Return unique notification types allowed for the given module codes."""
    accessible_module_codes = set(module_codes)
    accessible_module_codes.update(['notifications', Notification.ModuleContext.GENERAL])

    type_to_module = get_notification_type_to_module_mapping()
    allowed_types = []
    seen_codes = set()

    for choice in Notification.NotificationType.choices:
        notif_type_code = choice[0]
        module_context = type_to_module.get(notif_type_code, Notification.ModuleContext.GENERAL)
        module_context_value = module_context.value if hasattr(module_context, 'value') else module_context

        if module_context_value == '_superadmin_only':
            if not include_superadmin_only:
                continue
        elif module_context_value != Notification.ModuleContext.GENERAL.value:
            if module_context_value not in accessible_module_codes:
                continue

        if notif_type_code in seen_codes:
            continue

        allowed_types.append(choice)
        seen_codes.add(notif_type_code)

    return allowed_types


def get_allowed_notification_types_for_user(user):
    """
    Get notification types that a user is allowed to see based on their accessible modules.
    
    Args:
        user: The current user
        
    Returns:
        list: Tuple list of (code, label) for allowed notification types
    """
    if user.is_superuser:
        # Superusers see only notification types that match the modules exposed in the sidebar,
        # plus superadmin-only alerts.
        accessible_module_codes = Notification.visible_module_contexts_for_user(user)
        return _get_allowed_notification_types_from_modules(
            accessible_module_codes,
            include_superadmin_only=True,
        )
    
    if user.is_pet_owner():
        # Pet owners see limited notification types
        pet_owner_types = [
            Notification.NotificationType.APPOINTMENT,
            Notification.NotificationType.APPOINTMENT_REMINDER_1,
            Notification.NotificationType.APPOINTMENT_REMINDER_2,
            Notification.NotificationType.FOLLOW_UP,
            Notification.NotificationType.MEDICAL_RECORD_UPDATE,
            Notification.NotificationType.PRODUCT_RESERVATION,
            Notification.NotificationType.STATEMENT_RELEASED,
            Notification.NotificationType.GENERAL,
        ]
        return [
            (choice[0], choice[1]) for choice in Notification.NotificationType.choices
            if choice[0] in pet_owner_types
        ]
    
    # Staff members see notification types matching their accessible modules
    if user.assigned_role:
        accessible_module_codes = Notification.visible_module_contexts_for_user(user)
        allowed_types = _get_allowed_notification_types_from_modules(accessible_module_codes)

        # SOA notifications should only be visible to receptionists and branch admins.
        if getattr(user.assigned_role, 'code', None) not in ('receptionist', 'branch_admin'):
            allowed_types = [
                choice for choice in allowed_types
                if choice[0] != Notification.NotificationType.STATEMENT_RELEASED
            ]

        return allowed_types
    
    # Fallback: no notification types if no role
    return []


@login_required
def user_notifications(request):
    """List all notifications for the current user."""
    notifications = Notification.scoped_for_user(request.user).order_by('-created_at')
    unread_count = notifications.filter(is_read=False).count()

    current_filter = request.GET.get('filter', 'all')
    if current_filter == 'unread':
        notifications = notifications.filter(is_read=False)
    elif current_filter == 'read':
        notifications = notifications.filter(is_read=True)
    
    # Filter by notification type
    notif_type = request.GET.get('type', '')
    if notif_type and notif_type != 'all':
        notifications = notifications.filter(notification_type=notif_type)

    search_value = request.GET.get('q', '').strip()
    if search_value:
        notifications = notifications.filter(
            Q(title__icontains=search_value)
            | Q(message__icontains=search_value)
            | Q(notification_type__icontains=search_value)
        )

    # Pagination - 10 per page
    paginator = Paginator(notifications, 10)
    page_num = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_num)

    tab_list = [
        {'id': 'all', 'label': 'All', 'icon': 'bx-list-ul', 'url': f'?filter=all&type={notif_type}'},
        {'id': 'unread', 'label': 'Unread', 'icon': 'bx-envelope', 'count': unread_count, 'url': f'?filter=unread&type={notif_type}'},
        {'id': 'read', 'label': 'Read', 'icon': 'bx-envelope-open', 'url': f'?filter=read&type={notif_type}'},
    ]

    # Get notification types based on user's role and accessible modules
    notification_types = get_allowed_notification_types_for_user(request.user)

    return render(request, 'notifications/notification_list.html', {
        'page_obj': page_obj,
        'notifications': page_obj.object_list,
        'unread_count': unread_count,
        'current_filter': current_filter,
        'notif_type': notif_type,
        'notification_types': notification_types,
        'tab_list': tab_list,
        'search_value': search_value,
    })



@login_required
@require_POST
def mark_read(request, pk):
    """Mark a notification as read (AJAX endpoint)."""
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.is_read = True
    notification.save(update_fields=['is_read'])
    unread_count = Notification.scoped_for_user(request.user).filter(is_read=False).count()
    return JsonResponse({'success': True, 'unread_count': unread_count})


@login_required
@require_POST
def mark_all_read(request):
    """Mark all notifications as read."""
    updated = Notification.objects.filter(
        user=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'success': True, 'updated': updated, 'unread_count': 0})


@login_required
@require_POST
def delete_notification(request, pk):
    """Delete a single notification."""
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.delete()
    unread_count = Notification.scoped_for_user(request.user).filter(is_read=False).count()
    return JsonResponse({'success': True, 'unread_count': unread_count})


@login_required
@require_POST
def delete_all_notifications(request):
    """Delete all notifications for current user."""
    deleted, _ = Notification.objects.filter(user=request.user).delete()
    return JsonResponse({'success': True, 'deleted': deleted, 'unread_count': 0})


@login_required
@module_permission_required('notifications', 'VIEW')
def admin_notification_list(request):
    """List all notifications for the current admin user."""
    notifications = Notification.scoped_for_user(request.user).order_by('-created_at')
    unread_count = notifications.filter(is_read=False).count()

    current_filter = request.GET.get('filter', 'all')
    if current_filter == 'unread':
        notifications = notifications.filter(is_read=False)
    elif current_filter == 'read':
        notifications = notifications.filter(is_read=True)
    
    # Filter by notification type
    notif_type = request.GET.get('type', '')
    if notif_type and notif_type != 'all':
        notifications = notifications.filter(notification_type=notif_type)

    search_value = request.GET.get('q', '').strip()
    if search_value:
        notifications = notifications.filter(
            Q(title__icontains=search_value)
            | Q(message__icontains=search_value)
            | Q(notification_type__icontains=search_value)
        )

    # Pagination - 10 per page
    paginator = Paginator(notifications, 10)
    page_num = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_num)

    tab_list = [
        {'id': 'all', 'label': 'All', 'icon': 'bx-list-ul', 'url': f'?filter=all&type={notif_type}'},
        {'id': 'unread', 'label': 'Unread', 'icon': 'bx-envelope', 'count': unread_count, 'url': f'?filter=unread&type={notif_type}'},
        {'id': 'read', 'label': 'Read', 'icon': 'bx-envelope-open', 'url': f'?filter=read&type={notif_type}'},
    ]

    # Get notification types based on user's role and accessible modules
    notification_types = get_allowed_notification_types_for_user(request.user)

    return render(request, 'notifications/admin_notification_list.html', {
        'page_obj': page_obj,
        'notifications': page_obj.object_list,
        'unread_count': unread_count,
        'current_filter': current_filter,
        'notif_type': notif_type,
        'notification_types': notification_types,
        'tab_list': tab_list,
        'search_value': search_value,
    })
