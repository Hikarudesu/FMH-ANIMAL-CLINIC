from .models import Notification
from appointments.models import Appointment
from django.db.models import Count


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
        unread_by_module = {
            module_code: 0
            for module_code, _label in Notification.ModuleContext.choices
        }
        unread_by_module.update({
            row['module_context']: row['count']
            for row in unread_qs.values('module_context').annotate(count=Count('pk'))
        })

        context = {
            'recent_notifications': notifications,
            'unread_notifications_count': unread_count,
            'unread_notifications_by_module': unread_by_module,
            'unread_inventory_notifications_count': unread_by_module.get('inventory', 0),
            'unread_inquiry_notifications_count': unread_by_module.get('inquiries', 0),
            'unread_pet_notifications_count': (
                unread_by_module.get('patients', 0)
                + unread_by_module.get('medical_records', 0)
            ),
            'unread_pos_notifications_count': unread_by_module.get('soa', 0),
        }
        if request.user.is_clinic_staff():
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
