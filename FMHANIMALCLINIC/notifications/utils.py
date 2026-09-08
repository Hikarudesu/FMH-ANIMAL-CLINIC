"""Utility functions for creating and managing notifications."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from notifications.models import Notification
from notifications.delivery import send_notification_email, send_notification_sms


def _notify_superadmins(title, message, notification_type, module_context, related_object_id=None):
    from accounts.models import User

    superadmins = User.objects.filter(is_superuser=True)
    superadmin_emails = []

    for admin in superadmins:
        create_notification(
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


def create_notification(
    *,
    user,
    title,
    message,
    notification_type,
    module_context,
    related_object_id=None,
    related_follow_up=None,
    dedupe_window_minutes=15,
):
    """Create a notification safely with duplicate suppression and commit-time dispatch."""
    if user is None:
        return None

    safe_title = (title or 'Notification').strip()[:200]
    safe_message = (message or 'You have a new notification.').strip()

    dedupe_window = timezone.now() - timedelta(minutes=dedupe_window_minutes)
    existing = Notification.objects.filter(
        user=user,
        notification_type=notification_type,
        module_context=module_context,
        related_object_id=related_object_id,
        related_follow_up=related_follow_up,
        title=safe_title,
        message=safe_message,
        created_at__gte=dedupe_window,
    ).first()
    if existing:
        return existing

    payload = {
        'user': user,
        'title': safe_title,
        'message': safe_message,
        'notification_type': notification_type,
        'module_context': module_context,
        'related_object_id': related_object_id,
        'related_follow_up': related_follow_up,
    }

    created = {'obj': None}

    def _create_after_commit():
        created['obj'] = Notification.objects.create(**payload)

    transaction.on_commit(_create_after_commit)
    return created['obj']


def notify_role_users(
    *,
    role_code,
    branch,
    title,
    message,
    notification_type,
    module_context,
    related_object_id=None,
):
    """Send the same notification to users in a specific role and branch."""
    from accounts.models import User

    users = User.objects.filter(
        is_active=True,
        assigned_role__code=role_code,
    )
    if branch is not None:
        users = users.filter(branch=branch)

    for target in users:
        create_notification(
            user=target,
            title=title,
            message=message,
            notification_type=notification_type,
            module_context=module_context,
            related_object_id=related_object_id,
        )


def notify_inquiry_received(inquiry):
    """Create a notification when a new inquiry is received."""
    branch_name = inquiry.branch.name if inquiry.branch else 'all branches'
    message = (
        f"A new inquiry was submitted by {inquiry.full_name} for {branch_name}. "
        f"Priority: {inquiry.get_priority_display()}."
    )
    
    # Notify superadmins
    _notify_superadmins(
        title='New Inquiry Received',
        message=message,
        notification_type=Notification.NotificationType.INQUIRY_NEW,
        module_context=Notification.ModuleContext.INQUIRIES,
        related_object_id=inquiry.id,
    )
    
    # Notify receptionists in the same branch
    if inquiry.branch:
        notify_role_users(
            role_code='cashier',
            branch=inquiry.branch,
            title='New Inquiry Received',
            message=message,
            notification_type=Notification.NotificationType.INQUIRY_NEW,
            module_context=Notification.ModuleContext.INQUIRIES,
            related_object_id=inquiry.id,
        )


def notify_inquiry_responded(inquiry, responder=None):
    """Create a notification when an inquiry is responded to."""
    responder_name = ((responder.get_full_name() or responder.username) if responder else 'a staff member')
    message = f'Inquiry from {inquiry.full_name} was marked responded by {responder_name}.'
    
    # Notify superadmins
    _notify_superadmins(
        title='Inquiry Responded',
        message=message,
        notification_type=Notification.NotificationType.INQUIRY_RESPONDED,
        module_context=Notification.ModuleContext.INQUIRIES,
        related_object_id=inquiry.id,
    )
    
    # Notify receptionists in the same branch
    if inquiry.branch:
        notify_role_users(
            role_code='cashier',
            branch=inquiry.branch,
            title='Inquiry Responded',
            message=message,
            notification_type=Notification.NotificationType.INQUIRY_RESPONDED,
            module_context=Notification.ModuleContext.INQUIRIES,
            related_object_id=inquiry.id,
        )


def notify_inquiry_archived(inquiry, actor=None):
    """Create a notification when an inquiry is archived."""
    actor_name = ((actor.get_full_name() or actor.username) if actor else 'a staff member')
    message = f'Inquiry from {inquiry.full_name} was archived by {actor_name}.'
    
    # Notify superadmins
    _notify_superadmins(
        title='Inquiry Archived',
        message=message,
        notification_type=Notification.NotificationType.INQUIRY_ARCHIVED,
        module_context=Notification.ModuleContext.INQUIRIES,
        related_object_id=inquiry.id,
    )
    
    # Notify receptionists in the same branch
    if inquiry.branch:
        notify_role_users(
            role_code='cashier',
            branch=inquiry.branch,
            title='Inquiry Archived',
            message=message,
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


def notify_statement_released(statement):
    """Create notification when statement is released to both customer and receptionists."""
    if statement.customer:
        # Notify the customer
        create_notification(
            user=statement.customer,
            title="Statement Available",
            message=f"Your Statement of Account is now available. Total amount due: ₱{statement.total_amount}",
            notification_type=Notification.NotificationType.STATEMENT_RELEASED,
            module_context=Notification.ModuleContext.SOA,
            related_object_id=statement.id
        )
        
        # Notify receptionists in the branch (for customer follow-up and collection tracking)
        if hasattr(statement, 'branch') and statement.branch:
            branch = statement.branch
        elif hasattr(statement.customer, 'branch'):
            branch = statement.customer.branch
        else:
            branch = None
        
        if branch:
            customer_name = statement.customer.get_full_name() or statement.customer.username
            notify_role_users(
                role_code='cashier',
                branch=branch,
                title='Customer Statement Released',
                message=f"Statement released for {customer_name}. Amount due: ₱{statement.total_amount}",
                notification_type=Notification.NotificationType.STATEMENT_RELEASED,
                module_context=Notification.ModuleContext.SOA,
                related_object_id=statement.id,
            )


def notify_appointment_status_change(appointment, status, actor=None):
    """Create standardized customer notifications for appointment status changes."""
    if not appointment.user:
        return

    actor_label = 'clinic staff'
    if actor is not None:
        actor_label = actor.get_full_name() or actor.username

    if status == 'CONFIRMED':
        title = f'Appointment Confirmed for {appointment.pet_name}'
        message = (
            f'Your appointment for {appointment.pet_name} has been confirmed for '
            f"{appointment.appointment_date.strftime('%B %d, %Y')} at "
            f"{appointment.appointment_time.strftime('%I:%M %p')} at {appointment.branch.name}."
        )
    elif status == 'COMPLETED':
        title = f'Appointment Completed for {appointment.pet_name}'
        message = (
            f"Your appointment for {appointment.pet_name} on {appointment.appointment_date.strftime('%B %d, %Y')} "
            f'was marked completed by {actor_label}.'
        )
    elif status == 'CANCELLED':
        title = f'Appointment Cancelled for {appointment.pet_name}'
        message = (
            f'Your appointment for {appointment.pet_name} scheduled on '
            f"{appointment.appointment_date.strftime('%B %d, %Y')} at "
            f"{appointment.appointment_time.strftime('%I:%M %p')} was cancelled by {actor_label}."
        )
    else:
        return

    create_notification(
        user=appointment.user,
        title=title,
        message=message,
        notification_type=Notification.NotificationType.APPOINTMENT,
        module_context=Notification.ModuleContext.APPOINTMENTS,
        related_object_id=appointment.id,
    )


def notify_staff_appointment_status_change(appointment, status, actor=None):
    """
    Create staff notifications for appointment status changes.
    Notifies receptionists, vet assistants, and veterinarians who have appointments module access.
    """
    from accounts.models import User
    
    actor_label = 'clinic staff'
    if actor is not None:
        actor_label = actor.get_full_name() or actor.username

    if status == 'CONFIRMED':
        title = f'Appointment Confirmed: {appointment.pet_name}'
        message = (
            f'Appointment for {appointment.pet_name} has been confirmed for '
            f"{appointment.appointment_date.strftime('%B %d, %Y')} at "
            f"{appointment.appointment_time.strftime('%I:%M %p')}."
        )
    elif status == 'COMPLETED':
        title = f'Appointment Completed: {appointment.pet_name}'
        message = (
            f"Appointment for {appointment.pet_name} on {appointment.appointment_date.strftime('%B %d, %Y')} "
            f'was marked completed by {actor_label}.'
        )
    elif status == 'CANCELLED':
        title = f'Appointment Cancelled: {appointment.pet_name}'
        message = (
            f'Appointment for {appointment.pet_name} scheduled on '
            f"{appointment.appointment_date.strftime('%B %d, %Y')} at "
            f"{appointment.appointment_time.strftime('%I:%M %p')} was cancelled by {actor_label}."
        )
    else:
        return

    # Track users already notified
    notified_user_ids = set()

    # Notify receptionists in the same branch
    receptionists = User.objects.filter(
        is_active=True,
        assigned_role__code='cashier',
        branch=appointment.branch,
    )
    
    for receptionist in receptionists:
        create_notification(
            user=receptionist,
            title=title,
            message=message,
            notification_type=Notification.NotificationType.APPOINTMENT,
            module_context=Notification.ModuleContext.APPOINTMENTS,
            related_object_id=appointment.id,
        )
        notified_user_ids.add(receptionist.id)

    # Notify vet assistants in the same branch
    vet_assistants = User.objects.filter(
        is_active=True,
        assigned_role__code='assistant_veterinarian',
        branch=appointment.branch,
    ).exclude(id__in=notified_user_ids)
    
    for vet_assistant in vet_assistants:
        create_notification(
            user=vet_assistant,
            title=title,
            message=message,
            notification_type=Notification.NotificationType.APPOINTMENT,
            module_context=Notification.ModuleContext.APPOINTMENTS,
            related_object_id=appointment.id,
        )
        notified_user_ids.add(vet_assistant.id)

    # Notify veterinarians in the same branch
    veterinarians = User.objects.filter(
        is_active=True,
        assigned_role__code='veterinarian',
        branch=appointment.branch,
    ).exclude(id__in=notified_user_ids)

    for veterinarian in veterinarians:
        create_notification(
            user=veterinarian,
            title=title,
            message=message,
            notification_type=Notification.NotificationType.APPOINTMENT,
            module_context=Notification.ModuleContext.APPOINTMENTS,
            related_object_id=appointment.id,
        )
        notified_user_ids.add(veterinarian.id)


def notify_follow_up_scheduled(appointment, followup, follow_up_reason=''):
    """Create customer notification for a newly-scheduled follow-up."""
    if not appointment.user:
        return

    date_str = str(followup.follow_up_date)
    if followup.follow_up_end_date and followup.follow_up_end_date != followup.follow_up_date:
        date_str = f"{followup.follow_up_date} to {followup.follow_up_end_date}"

    create_notification(
        user=appointment.user,
        title=f'Follow-up Scheduled for {appointment.pet_name}',
        message=(
            f'A follow-up visit has been scheduled for {appointment.pet_name} '
            f'from {date_str}. Reason: {follow_up_reason or "Routine follow-up"}'
        ),
        notification_type=Notification.NotificationType.FOLLOW_UP,
        module_context=Notification.ModuleContext.APPOINTMENTS,
        related_object_id=appointment.id,
        related_follow_up=followup,
    )


def notify_reservation_approved(reservation, actor=None):
    """Create a notification when a product reservation is approved."""
    actor_name = ((actor.get_full_name() or actor.username) if actor else 'staff')
    customer_name = reservation.user.get_full_name() or reservation.user.username
    message = f"Product reservation for {customer_name} ({reservation.product.name} x{reservation.quantity}) has been approved."
    
    # Notify receptionists in the product's branch
    notify_role_users(
        role_code='cashier',
        branch=reservation.product.branch,
        title='Reservation Approved',
        message=message,
        notification_type=Notification.NotificationType.RESERVATION_APPROVED,
        module_context=Notification.ModuleContext.INVENTORY,
        related_object_id=reservation.id,
    )


def notify_reservation_ready(reservation, actor=None):
    """Create a notification when a product reservation is ready for pickup."""
    customer_name = reservation.user.get_full_name() or reservation.user.username
    message = f"Your reservation for {reservation.product.name} (x{reservation.quantity}) is ready for pickup."
    
    # Notify the customer
    create_notification(
        user=reservation.user,
        title='Reservation Ready for Pickup',
        message=message,
        notification_type=Notification.NotificationType.RESERVATION_READY,
        module_context=Notification.ModuleContext.INVENTORY,
        related_object_id=reservation.id,
    )
    
    # Notify receptionists in the product's branch (to handle pickup)
    notify_role_users(
        role_code='cashier',
        branch=reservation.product.branch,
        title='Reservation Ready for Pickup',
        message=f"Reservation ready for {customer_name}: {reservation.product.name} (x{reservation.quantity})",
        notification_type=Notification.NotificationType.RESERVATION_READY,
        module_context=Notification.ModuleContext.INVENTORY,
        related_object_id=reservation.id,
    )


def notify_reservation_rejected(reservation, actor=None):
    """Create a notification when a product reservation is rejected."""
    actor_name = ((actor.get_full_name() or actor.username) if actor else 'staff')
    customer_name = reservation.user.get_full_name() or reservation.user.username
    message = f"Your reservation for {reservation.product.name} (x{reservation.quantity}) has been rejected."
    
    # Notify the customer
    create_notification(
        user=reservation.user,
        title='Reservation Rejected',
        message=message,
        notification_type=Notification.NotificationType.RESERVATION_REJECTED,
        module_context=Notification.ModuleContext.INVENTORY,
        related_object_id=reservation.id,
    )
    
    # Notify receptionists in the product's branch
    notify_role_users(
        role_code='cashier',
        branch=reservation.product.branch,
        title='Reservation Rejected',
        message=f"Reservation rejected for {customer_name}: {reservation.product.name} (x{reservation.quantity})",
        notification_type=Notification.NotificationType.RESERVATION_REJECTED,
        module_context=Notification.ModuleContext.INVENTORY,
        related_object_id=reservation.id,
    )
