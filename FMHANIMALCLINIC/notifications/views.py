from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Q
from django.urls import reverse

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
        
        Notification.NotificationType.STOCK_TRANSFER_REQUESTED: Notification.ModuleContext.INVENTORY,
        Notification.NotificationType.STOCK_TRANSFER_APPROVED: Notification.ModuleContext.INVENTORY,
        Notification.NotificationType.STOCK_TRANSFER_REJECTED: Notification.ModuleContext.INVENTORY,
        Notification.NotificationType.STOCK_TRANSFER_COMPLETED: Notification.ModuleContext.INVENTORY,
        
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
            Notification.NotificationType.APPOINTMENT_RESCHEDULED,
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
        if getattr(user.assigned_role, 'code', None) not in ('cashier', 'executive_officer'):
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
    return _render_notification_list(request, 'notifications/notification_list.html')


def _render_notification_list(request, template_name):
    """Render the shared Primary/Updates inbox for either portal."""
    notifications = Notification.scoped_for_user(request.user).order_by('-created_at')
    unread_count = notifications.filter(is_read=False).count()
    unread_primary_count = notifications.filter(
        is_read=False,
        inbox_category=Notification.InboxCategory.PRIMARY,
    ).count()
    unread_updates_count = notifications.filter(
        is_read=False,
        inbox_category=Notification.InboxCategory.UPDATES,
    ).count()

    current_filter = request.GET.get('filter', 'primary')
    if current_filter not in {
        Notification.InboxCategory.PRIMARY,
        Notification.InboxCategory.UPDATES,
    }:
        current_filter = Notification.InboxCategory.PRIMARY
    notifications = notifications.filter(inbox_category=current_filter)

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

    paginator = Paginator(notifications, 10)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    tab_list = [
        {
            'id': Notification.InboxCategory.PRIMARY,
            'label': 'Primary',
            'icon': 'bx-inbox',
            'count': unread_primary_count,
            'url': f'?filter=PRIMARY&type={notif_type}',
        },
        {
            'id': Notification.InboxCategory.UPDATES,
            'label': 'Updates',
            'icon': 'bx-bell',
            'count': unread_updates_count,
            'url': f'?filter=UPDATES&type={notif_type}',
        },
    ]

    return render(request, template_name, {
        'page_obj': page_obj,
        'notifications': page_obj.object_list,
        'unread_count': unread_count,
        'unread_primary_count': unread_primary_count,
        'unread_updates_count': unread_updates_count,
        'current_filter': current_filter,
        'notif_type': notif_type,
        'notification_types': get_allowed_notification_types_for_user(request.user),
        'tab_list': tab_list,
        'search_value': search_value,
    })


def _notification_destination(notification, user):
    """Resolve a notification to its owned record or a safe module fallback."""
    module_context = notification.module_context
    related_id = notification.related_object_id

    if module_context == Notification.ModuleContext.APPOINTMENTS:
        if user.is_pet_owner():
            from appointments.models import Appointment

            if related_id and Appointment.objects.filter(
                pk=related_id, user=user
            ).exists():
                return reverse('appointments:portal_detail', args=[related_id])
            return reverse('appointments:my_appointments')
        if user.has_navigation_module_access('appointments'):
            from appointments.models import Appointment

            if related_id and Appointment.objects.filter(pk=related_id).exists():
                return reverse('appointments:admin_detail', args=[related_id])
            return reverse('appointments:admin_list')

    elif module_context == Notification.ModuleContext.INQUIRIES:
        if not user.is_superuser and user.has_module_permission('inquiries', 'VIEW'):
            from inquiries.models import Inquiry

            if related_id and Inquiry.objects.filter(pk=related_id).exists():
                return reverse('inquiries:detail', args=[related_id])
            return reverse('inquiries:list')

    elif module_context == Notification.ModuleContext.MEDICAL_RECORDS:
        from records.models import MedicalRecord

        record = MedicalRecord.objects.filter(pk=related_id).select_related(
            'pet__owner'
        ).first() if related_id else None
        if user.is_pet_owner():
            if record and record.pet.owner_id == user.pk:
                return reverse('records:user_detail', args=[related_id])
            return reverse('patients:my_pets')
        if user.has_navigation_module_access('medical_records'):
            if record:
                return reverse('records:admin_detail', args=[related_id])
            return reverse('records:admin_list')

    elif module_context == Notification.ModuleContext.INVENTORY:
        if user.is_pet_owner():
            from inventory.models import Reservation

            if notification.notification_type in {
                Notification.NotificationType.PRODUCT_RESERVATION,
                Notification.NotificationType.RESERVATION_APPROVED,
                Notification.NotificationType.RESERVATION_REJECTED,
                Notification.NotificationType.RESERVATION_READY,
            }:
                if related_id and Reservation.objects.filter(
                    pk=related_id, user=user
                ).exists():
                    return reverse('inventory:reservation_success', args=[related_id])
                return reverse('inventory:my_reservations')
            return reverse('inventory:catalog')
        if user.has_navigation_module_access('inventory'):
            if notification.notification_type in {
                Notification.NotificationType.STOCK_TRANSFER_REQUESTED,
                Notification.NotificationType.STOCK_TRANSFER_APPROVED,
                Notification.NotificationType.STOCK_TRANSFER_REJECTED,
                Notification.NotificationType.STOCK_TRANSFER_COMPLETED,
            }:
                return reverse('inventory:transfer_list')
            from inventory.models import Product

            if notification.notification_type in {
                Notification.NotificationType.PRODUCT_RESERVATION,
                Notification.NotificationType.RESERVATION_APPROVED,
                Notification.NotificationType.RESERVATION_REJECTED,
                Notification.NotificationType.RESERVATION_READY,
            }:
                return reverse('inventory:management')
            if related_id and Product.objects.filter(pk=related_id).exists():
                if user.has_module_permission('inventory', 'MANAGE'):
                    return reverse('inventory:product_edit', args=[related_id])
            return reverse('inventory:management')

    elif module_context == Notification.ModuleContext.SOA:
        if user.is_pet_owner():
            from billing.models import CustomerStatement

            if related_id and CustomerStatement.objects.filter(
                pk=related_id, customer=user
            ).exists():
                return reverse('billing:my_statement_detail', args=[related_id])
            return reverse('billing:my_statements')
        if user.has_navigation_special_permission('can_access_pos'):
            return reverse('pos:sales_list')

    elif module_context == Notification.ModuleContext.PATIENTS:
        if user.is_pet_owner():
            return reverse('patients:my_pets')
        if user.has_navigation_module_access('patients'):
            return reverse('patients:admin_list')
    elif module_context == Notification.ModuleContext.AI_DIAGNOSTICS:
        if user.has_navigation_module_access('ai_diagnostics'):
            return reverse('diagnostics:dashboard')
    elif module_context == Notification.ModuleContext.PAYROLL:
        if user.has_navigation_module_access('payroll'):
            return reverse('payroll:dashboard')

    return reverse('notifications:notification_list')


@login_required
def open_notification(request, pk):
    """Mark a visible notification read and open its related record."""
    notification = get_object_or_404(
        Notification.scoped_for_user(request.user),
        pk=pk,
    )
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=['is_read'])

    return redirect(_notification_destination(notification, request.user))



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
    deleted, _ = Notification.objects.filter(pk=pk, user=request.user).delete()
    if not deleted:
        return JsonResponse({'success': False, 'error': 'Notification not found'}, status=404)

    unread_count = Notification.scoped_for_user(request.user).filter(is_read=False).count()
    return JsonResponse({'success': True, 'deleted': deleted, 'unread_count': unread_count})


@login_required
@require_POST
def delete_all_notifications(request):
    """Delete all notifications for current user."""
    deleted, _ = Notification.objects.filter(user=request.user).delete()
    return JsonResponse({'success': True, 'deleted': deleted, 'unread_count': 0})


@login_required
def admin_notification_list(request):
    """List all notifications for the current staff user's account."""
    return _render_notification_list(request, 'notifications/admin_notification_list.html')
