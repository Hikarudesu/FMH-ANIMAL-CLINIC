from .models import Notification


def unread_notifications(request):
    """
    Returns the 5 most recent unread notifications for the authenticated user.
    Optimized to use a single query for both notifications and count.
    """
    if request.user.is_authenticated:
        # Single query - get all unread, slice for display, len for count
        unread_qs = Notification.scoped_for_user(request.user).filter(
            is_read=False
        ).order_by('-created_at')

        # Evaluate once and reuse
        notifications = list(unread_qs[:5])
        unread_count = unread_qs.count()

        return {
            'recent_notifications': notifications,
            'unread_notifications_count': unread_count
        }
    return {}
