"""Utility functions for creating and managing notifications."""

from notifications.models import Notification
from notifications.delivery import send_notification_email, send_notification_sms


def _notify_superadmins(title, message, notification_type, module_context, related_object_id=None):
    from accounts.models import User

    superadmins = User.objects.filter(is_superuser=True)
    superadmin_emails = []

    for admin in superadmins:
        Notification.objects.create(
            user=admin,
            title=title,
            message=message,
            notification_type=notification_type,
            module_context=module_context,
            related_object_id=related_object_id,
        )
        if admin.email:
            superadmin_emails.append(admin.email)

    if superadmin_emails:
        admin_email_body = (
            f"{message}\n\n"
            f"Internal Context (Superuser):\n"
            f"- Type: {notification_type}\n"
            f"- Module: {module_context}\n"
            f"- Related Object ID: {related_object_id or 'N/A'}\n"
        )
        send_notification_email(
            subject=f"[Superuser Alert] {title}",
            message=admin_email_body,
            recipient_list=superadmin_emails,
            superuser_only=True,
            fail_silently=True,
        )

    send_notification_sms(message=f"{title}: {message}")


def notify_inquiry_received(inquiry):
    """Create a notification when a new inquiry is received."""
    branch_name = inquiry.branch.name if inquiry.branch else 'all branches'
    _notify_superadmins(
        title='New Inquiry Received',
        message=(
            f"A new inquiry was submitted by {inquiry.full_name} for {branch_name}. "
            f"Priority: {inquiry.get_priority_display()}."
        ),
        notification_type=Notification.NotificationType.INQUIRY_NEW,
        module_context=Notification.ModuleContext.INQUIRIES,
        related_object_id=inquiry.id,
    )


def notify_inquiry_responded(inquiry, responder=None):
    """Create a notification when an inquiry is responded to."""
    responder_name = ((responder.get_full_name() or responder.username) if responder else 'a staff member')
    _notify_superadmins(
        title='Inquiry Responded',
        message=f'Inquiry from {inquiry.full_name} was marked responded by {responder_name}.',
        notification_type=Notification.NotificationType.INQUIRY_RESPONDED,
        module_context=Notification.ModuleContext.INQUIRIES,
        related_object_id=inquiry.id,
    )


def notify_inquiry_archived(inquiry, actor=None):
    """Create a notification when an inquiry is archived."""
    actor_name = ((actor.get_full_name() or actor.username) if actor else 'a staff member')
    _notify_superadmins(
        title='Inquiry Archived',
        message=f'Inquiry from {inquiry.full_name} was archived by {actor_name}.',
        notification_type=Notification.NotificationType.INQUIRY_ARCHIVED,
        module_context=Notification.ModuleContext.INQUIRIES,
        related_object_id=inquiry.id,
    )


def notify_stock_transfer_requested(transfer):
    """Create a notification when a new stock transfer is requested."""
    _notify_superadmins(
        title='Stock Transfer Requested',
        message=(
            f"{transfer.requested_by.get_full_name() or transfer.requested_by.username} requested "
            f"{transfer.quantity}x {transfer.source_product.name} from {transfer.source_product.branch.name} "
            f"to {transfer.destination_branch.name}."
        ),
        notification_type=Notification.NotificationType.STOCK_TRANSFER_REQUESTED,
        module_context=Notification.ModuleContext.INVENTORY,
        related_object_id=transfer.id,
    )


def notify_stock_transfer_approved(transfer, actor=None):
    """Create a notification when a stock transfer is approved."""
    actor_name = ((actor.get_full_name() or actor.username) if actor else 'a staff member')
    _notify_superadmins(
        title='Stock Transfer Approved',
        message=(
            f"Transfer #{transfer.pk} for {transfer.quantity}x {transfer.source_product.name} "
            f"was approved by {actor_name}."
        ),
        notification_type=Notification.NotificationType.STOCK_TRANSFER_APPROVED,
        module_context=Notification.ModuleContext.INVENTORY,
        related_object_id=transfer.id,
    )


def notify_stock_transfer_rejected(transfer, actor=None):
    """Create a notification when a stock transfer is rejected."""
    actor_name = ((actor.get_full_name() or actor.username) if actor else 'a staff member')
    _notify_superadmins(
        title='Stock Transfer Rejected',
        message=(
            f"Transfer #{transfer.pk} for {transfer.quantity}x {transfer.source_product.name} "
            f"was rejected by {actor_name}."
        ),
        notification_type=Notification.NotificationType.STOCK_TRANSFER_REJECTED,
        module_context=Notification.ModuleContext.INVENTORY,
        related_object_id=transfer.id,
    )


def notify_stock_transfer_completed(transfer, actor=None):
    """Create a notification when a stock transfer is completed."""
    actor_name = ((actor.get_full_name() or actor.username) if actor else 'a staff member')
    _notify_superadmins(
        title='Stock Transfer Completed',
        message=(
            f"Transfer #{transfer.pk} for {transfer.quantity}x {transfer.source_product.name} "
            f"was completed by {actor_name}."
        ),
        notification_type=Notification.NotificationType.STOCK_TRANSFER_COMPLETED,
        module_context=Notification.ModuleContext.INVENTORY,
        related_object_id=transfer.id,
    )


def notify_payroll_generated(period, actor=None, created_count=0, updated_count=0, total_employees=0):
    """Create a notification when payroll is generated."""
    actor_name = ((actor.get_full_name() or actor.username) if actor else 'a staff member')
    _notify_superadmins(
        title='Payroll Generated',
        message=(
            f"Payroll for {period.period_display} was generated by {actor_name}. "
            f"{created_count} new, {updated_count} updated, {total_employees} employees processed."
        ),
        notification_type=Notification.NotificationType.PAYROLL_GENERATED,
        module_context=Notification.ModuleContext.PAYROLL,
        related_object_id=period.id,
    )


def notify_payroll_released(period, actor=None, payslip_count=0, emails_sent=0):
    """Create a notification when payroll is released."""
    actor_name = ((actor.get_full_name() or actor.username) if actor else 'a staff member')
    _notify_superadmins(
        title='Payroll Released',
        message=(
            f"Payroll for {period.period_display} was released by {actor_name}. "
            f"{payslip_count} payslips processed, {emails_sent} emails sent."
        ),
        notification_type=Notification.NotificationType.PAYROLL_RELEASED,
        module_context=Notification.ModuleContext.PAYROLL,
        related_object_id=period.id,
    )


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
