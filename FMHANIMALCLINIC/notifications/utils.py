"""Utility functions for creating and managing notifications."""

from notifications.models import Notification


def notify_appointment_confirmed(appointment):
    """Create notification when appointment is confirmed."""
    if appointment.user:
        Notification.objects.create(
            user=appointment.user,
            title="Appointment Confirmed",
            message=f"Your appointment for {appointment.pet_name} on {appointment.appointment_date.strftime('%B %d, %Y')} at {appointment.appointment_time.strftime('%I:%M %p')} has been confirmed.",
            notification_type=Notification.NotificationType.APPOINTMENT_CONFIRMED,
            module_context=Notification.ModuleContext.APPOINTMENTS,
            related_object_id=appointment.id
        )


def notify_appointment_cancelled(appointment):
    """Create notification when appointment is cancelled."""
    if appointment.user:
        Notification.objects.create(
            user=appointment.user,
            title="Appointment Cancelled",
            message=f"Your appointment for {appointment.pet_name} on {appointment.appointment_date.strftime('%B %d, %Y')} has been cancelled.",
            notification_type=Notification.NotificationType.APPOINTMENT_CANCELLED,
            module_context=Notification.ModuleContext.APPOINTMENTS,
            related_object_id=appointment.id
        )


def notify_appointment_rescheduled(appointment, old_date, old_time):
    """Create notification when appointment is rescheduled."""
    if appointment.user:
        Notification.objects.create(
            user=appointment.user,
            title="Appointment Rescheduled",
            message=f"Your appointment for {appointment.pet_name} has been moved from {old_date.strftime('%B %d')} at {old_time.strftime('%I:%M %p')} to {appointment.appointment_date.strftime('%B %d, %Y')} at {appointment.appointment_time.strftime('%I:%M %p')}.",
            notification_type=Notification.NotificationType.APPOINTMENT_RESCHEDULED,
            module_context=Notification.ModuleContext.APPOINTMENTS,
            related_object_id=appointment.id
        )


def notify_reservation_approved(reservation):
    """Create notification when product reservation is approved."""
    if reservation.customer:
        Notification.objects.create(
            user=reservation.customer,
            title="Reservation Approved",
            message=f"Your reservation for {reservation.product.name} has been approved and is ready for pickup.",
            notification_type=Notification.NotificationType.RESERVATION_APPROVED,
            module_context=Notification.ModuleContext.INVENTORY,
            related_object_id=reservation.id
        )


def notify_reservation_rejected(reservation):
    """Create notification when product reservation is rejected."""
    if reservation.customer:
        Notification.objects.create(
            user=reservation.customer,
            title="Reservation Cancelled",
            message=f"Unfortunately, your reservation for {reservation.product.name} could not be fulfilled.",
            notification_type=Notification.NotificationType.RESERVATION_REJECTED,
            module_context=Notification.ModuleContext.INVENTORY,
            related_object_id=reservation.id
        )


def notify_reservation_ready(reservation):
    """Create notification when reserved product is ready for pickup."""
    if reservation.customer:
        Notification.objects.create(
            user=reservation.customer,
            title="Your Order Is Ready",
            message=f"Your reserved item {reservation.product.name} is now ready for pickup at {reservation.product.branch.name}.",
            notification_type=Notification.NotificationType.RESERVATION_READY,
            module_context=Notification.ModuleContext.INVENTORY,
            related_object_id=reservation.id
        )


def notify_follow_up_reminder(follow_up):
    """Create notification for follow-up reminder."""
    if follow_up.appointment.user:
        Notification.objects.create(
            user=follow_up.appointment.user,
            title="Follow-up Visit Reminder",
            message=f"Follow-up visit due for {follow_up.pet_name} on {follow_up.follow_up_date.strftime('%B %d, %Y')}. {follow_up.reason}",
            notification_type=Notification.NotificationType.FOLLOW_UP,
            module_context=Notification.ModuleContext.APPOINTMENTS,
            related_follow_up=follow_up
        )


def notify_follow_up_overdue(follow_up):
    """Create notification when follow-up is overdue."""
    if follow_up.appointment.user:
        Notification.objects.create(
            user=follow_up.appointment.user,
            title="Follow-up Visit Overdue",
            message=f"Your follow-up visit for {follow_up.pet_name} was due on {follow_up.follow_up_date.strftime('%B %d, %Y')}. Please schedule your appointment as soon as possible.",
            notification_type=Notification.NotificationType.FOLLOW_UP_OVERDUE,
            module_context=Notification.ModuleContext.APPOINTMENTS,
            related_follow_up=follow_up
        )


def notify_low_stock_alert(product):
    """Create notification for low stock alert."""
    from accounts.models import User
    # Notify all branch admins and superadmin
    admins = User.objects.filter(is_superuser=True)
    for admin in admins:
        Notification.objects.create(
            user=admin,
            title="Low Stock Alert",
            message=f"Stock for {product.name} (SKU: {product.sku}) is below minimum level. Current stock: {product.stock_quantity}. Minimum required: {product.min_stock_level}",
            notification_type=Notification.NotificationType.LOW_STOCK_ALERT,
            module_context=Notification.ModuleContext.INVENTORY,
            related_object_id=product.id
        )


def notify_statement_released(statement):
    """Create notification when statement is released."""
    if statement.customer:
        Notification.objects.create(
            user=statement.customer,
            title="Statement Available",
            message=f"Your Statement of Account is now available. Total amount due: ₱{statement.total_amount}",
            notification_type=Notification.NotificationType.STATEMENT_RELEASED,
            module_context=Notification.ModuleContext.SOA,
            related_object_id=statement.id
        )


def notify_medical_record_update(medical_record):
    """Create notification when medical record is updated."""
    if medical_record.pet.owner:
        Notification.objects.create(
            user=medical_record.pet.owner,
            title="Medical Record Updated",
            message=f"A new medical record has been created for {medical_record.pet.name}. Chief complaint: {medical_record.chief_complaint}",
            notification_type=Notification.NotificationType.MEDICAL_RECORD_UPDATE,
            module_context=Notification.ModuleContext.MEDICAL_RECORDS,
            related_object_id=medical_record.id
        )
