from .models import Notification
from appointments.models import Appointment


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

        context = {
            'recent_notifications': notifications,
            'unread_notifications_count': unread_count
        }
        if request.user.is_clinic_staff:
            pending_appointments = Appointment.objects.filter(
                status=Appointment.Status.PENDING
            )
            if not request.user.is_superuser:
                pending_appointments = pending_appointments.filter(
                    branch=request.user.branch
                )
        elif request.user.is_pet_owner():
            pending_appointments = Appointment.objects.filter(
                user=request.user,
                status=Appointment.Status.PENDING,
            )
        else:
            pending_appointments = Appointment.objects.none()
        context['pending_appointments_count'] = pending_appointments.count()
        return context
    return {}
