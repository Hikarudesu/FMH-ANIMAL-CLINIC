from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator

from .models import Notification
from accounts.decorators import module_permission_required


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

    # Pagination - 10 per page
    paginator = Paginator(notifications, 10)
    page_num = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_num)

    tab_list = [
        {'id': 'all', 'label': 'All', 'icon': 'bx-list-ul', 'url': f'?filter=all&type={notif_type}'},
        {'id': 'unread', 'label': 'Unread', 'icon': 'bx-envelope', 'count': unread_count, 'url': f'?filter=unread&type={notif_type}'},
        {'id': 'read', 'label': 'Read', 'icon': 'bx-envelope-open', 'url': f'?filter=read&type={notif_type}'},
    ]

    return render(request, 'notifications/notification_list.html', {
        'page_obj': page_obj,
        'notifications': page_obj.object_list,
        'unread_count': unread_count,
        'current_filter': current_filter,
        'notif_type': notif_type,
        'notification_types': Notification.NotificationType.choices,
        'tab_list': tab_list,
    })


@login_required
@require_POST
def mark_read(request, pk):
    """Mark a notification as read (AJAX endpoint)."""
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.is_read = True
    notification.save(update_fields=['is_read'])
    return JsonResponse({'success': True})


@login_required
@require_POST
def mark_all_read(request):
    """Mark all notifications as read."""
    Notification.objects.filter(
        user=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'success': True})


@login_required
@require_POST
def delete_notification(request, pk):
    """Delete a single notification."""
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.delete()
    return JsonResponse({'success': True})


@login_required
@require_POST
def delete_all_notifications(request):
    """Delete all notifications for current user."""
    Notification.objects.filter(user=request.user).delete()
    return JsonResponse({'success': True})


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

    # Pagination - 10 per page
    paginator = Paginator(notifications, 10)
    page_num = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_num)

    tab_list = [
        {'id': 'all', 'label': 'All', 'icon': 'bx-list-ul', 'url': f'?filter=all&type={notif_type}'},
        {'id': 'unread', 'label': 'Unread', 'icon': 'bx-envelope', 'count': unread_count, 'url': f'?filter=unread&type={notif_type}'},
        {'id': 'read', 'label': 'Read', 'icon': 'bx-envelope-open', 'url': f'?filter=read&type={notif_type}'},
    ]

    return render(request, 'notifications/admin_notification_list.html', {
        'page_obj': page_obj,
        'notifications': page_obj.object_list,
        'unread_count': unread_count,
        'current_filter': current_filter,
        'notif_type': notif_type,
        'notification_types': Notification.NotificationType.choices,
        'tab_list': tab_list,
    })
