"""Utility functions for creating and managing notifications."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date

from notifications.models import Notification
from notifications.delivery import send_notification_email


def mark_module_notifications_read(user, module_context):
    """Mark visible unread notifications for one module as read."""
    return Notification.scoped_for_user(user).filter(
        module_context=module_context,
        is_read=False,
    ).update(is_read=True)


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


def get_follow_up_owner(appointment):
    """Resolve the registered owner for an appointment, including legacy records."""
    if appointment is None:
        return None
    if appointment.user_id:
        return appointment.user
    if appointment.pet_id and appointment.pet and appointment.pet.owner_id:
        return appointment.pet.owner

    if appointment.owner_email:
        from accounts.models import User

        return User.objects.filter(
            email__iexact=appointment.owner_email.strip(),
            is_active=True,
        ).first()
    return None


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

    role_codes = role_code if isinstance(role_code, (tuple, list, set)) else (role_code,)
    if role_code == 'cashier':
        role_codes = (*role_codes, 'receptionist')

    users = User.objects.filter(
        is_active=True,
        assigned_role__code__in=role_codes,
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


def users_with_module_access(module_code, branch=None):
    """Return active staff users allowed to receive a module event."""
    from accounts.models import User
    from django.db.models import Q

    if module_code == 'reservations':
        users = User.objects.filter(
            is_active=True,
            assigned_role__module_permissions__module__code=module_code,
        )
    else:
        users = User.objects.filter(is_active=True).filter(
            Q(is_superuser=True)
            | Q(assigned_role__module_permissions__module__code=module_code)
        )
    if branch is not None:
        users = users.filter(Q(is_superuser=True) | Q(branch=branch))
    return users.distinct()


def notify_module_users(
    *, module_code, branch, title, message, notification_type,
    module_context, related_object_id=None, dedupe_window_minutes=15,
):
    """Notify every active user with access to a module in the branch scope."""
    targets = list(users_with_module_access(module_code, branch))
    for target in targets:
        create_notification(
            user=target,
            title=title,
            message=message,
            notification_type=notification_type,
            module_context=module_context,
            related_object_id=related_object_id,
            dedupe_window_minutes=dedupe_window_minutes,
        )
    return targets


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
    
    # Notify branch cashiers/receptionists. If no branch was selected, notify
    # all active cashiers so the inquiry is not left unowned.
    for role_code in ('cashier', 'executive_officer'):
        notify_role_users(
            role_code=role_code,
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
    
    for role_code in ('cashier', 'executive_officer'):
        notify_role_users(
            role_code=role_code,
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
    
    for role_code in ('cashier', 'executive_officer'):
        notify_role_users(
            role_code=role_code,
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


def _notify_stock_transfer_requester(transfer, *, title, message, notification_type):
    requester = transfer.requested_by
    if requester is None or requester.is_superuser:
        return
    create_notification(
        user=requester,
        title=title,
        message=message,
        notification_type=notification_type,
        module_context=Notification.ModuleContext.INVENTORY,
        related_object_id=transfer.id,
    )


def notify_stock_transfer_approved(transfer, actor=None):
    """Create a notification when a stock transfer is approved."""
    actor_name = ((actor.get_full_name() or actor.username) if actor else 'a staff member')
    title = 'Stock Transfer Approved'
    message = (
        f"Transfer #{transfer.pk} for {transfer.quantity}x {transfer.source_product.name} "
        f"was approved by {actor_name}."
    )
    notification_type = Notification.NotificationType.STOCK_TRANSFER_APPROVED
    _notify_superadmins(
        title=title,
        message=message,
        notification_type=notification_type,
        module_context=Notification.ModuleContext.INVENTORY,
        related_object_id=transfer.id,
    )
    _notify_stock_transfer_requester(
        transfer,
        title=title,
        message=message,
        notification_type=notification_type,
    )


def notify_stock_transfer_rejected(transfer, actor=None):
    """Create a notification when a stock transfer is rejected."""
    actor_name = ((actor.get_full_name() or actor.username) if actor else 'a staff member')
    title = 'Stock Transfer Rejected'
    message = (
        f"Transfer #{transfer.pk} for {transfer.quantity}x {transfer.source_product.name} "
        f"was rejected by {actor_name}."
    )
    notification_type = Notification.NotificationType.STOCK_TRANSFER_REJECTED
    _notify_superadmins(
        title=title,
        message=message,
        notification_type=notification_type,
        module_context=Notification.ModuleContext.INVENTORY,
        related_object_id=transfer.id,
    )
    _notify_stock_transfer_requester(
        transfer,
        title=title,
        message=message,
        notification_type=notification_type,
    )


def notify_stock_transfer_completed(transfer, actor=None):
    """Create a notification when a stock transfer is completed."""
    actor_name = ((actor.get_full_name() or actor.username) if actor else 'a staff member')
    title = 'Stock Transfer Completed'
    message = (
        f"Transfer #{transfer.pk} for {transfer.quantity}x {transfer.source_product.name} "
        f"was completed by {actor_name}."
    )
    notification_type = Notification.NotificationType.STOCK_TRANSFER_COMPLETED
    _notify_superadmins(
        title=title,
        message=message,
        notification_type=notification_type,
        module_context=Notification.ModuleContext.INVENTORY,
        related_object_id=transfer.id,
    )
    _notify_stock_transfer_requester(
        transfer,
        title=title,
        message=message,
        notification_type=notification_type,
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
    """Notify superadmins and staff when payroll is released."""
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

    for payslip in period.payslips.select_related('employee__user'):
        staff_user = payslip.employee.user if payslip.employee.user_id else None
        if not staff_user:
            continue
        create_notification(
            user=staff_user,
            title=f'Payslip Released - {period.period_display}',
            message=(
                f'Your payslip for {period.period_display} has been released. '
                'Your payslip has been sent to your registered email address.'
            ),
            notification_type=Notification.NotificationType.PAYROLL_RELEASED,
            module_context=Notification.ModuleContext.PAYROLL,
            related_object_id=payslip.id,
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


def notify_appointment_status_change(appointment, status, actor=None, actor_label=None):
    """Create standardized customer notifications for appointment status changes."""
    if not appointment.user:
        return

    if actor_label is None:
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

    if status == 'PENDING':
        title = f'New Appointment Request: {appointment.pet_name}'
        message = (
            f'Appointment request for {appointment.pet_name} is pending review for '
            f"{appointment.appointment_date.strftime('%B %d, %Y')} at "
            f"{appointment.appointment_time.strftime('%I:%M %p')}."
        )
    elif status == 'CONFIRMED':
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

    # Notify cashiers in the same branch. Include the legacy receptionist
    # role code for accounts created before the role rename.
    receptionists = User.objects.filter(
        is_active=True,
        assigned_role__code__in=('cashier', 'receptionist'),
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


def notify_veterinarian_medical_record_required(appointment, actor=None):
    """Notify the assigned veterinarian that a completed visit needs a record."""
    if not appointment or not appointment.preferred_vet_id:
        return

    veterinarian = getattr(appointment.preferred_vet, 'user', None)
    if not veterinarian or not veterinarian.is_active:
        return

    actor_label = 'clinic staff'
    if actor is not None:
        actor_label = actor.get_full_name() or actor.username

    create_notification(
        user=veterinarian,
        title=f'Medical Record Required: {appointment.pet_name}',
        message=(
            f'Appointment for {appointment.pet_name} on '
            f'{appointment.appointment_date.strftime("%B %d, %Y")} was marked completed '
            f'by {actor_label}. Please create the medical record.'
        ),
        notification_type=Notification.NotificationType.APPOINTMENT,
        module_context=Notification.ModuleContext.APPOINTMENTS,
        related_object_id=appointment.id,
        dedupe_window_minutes=60 * 24,
    )


def notify_follow_up_scheduled(
    appointment, followup, follow_up_reason='', event='scheduled'
):
    """Notify the owner about a scheduled or updated follow-up."""

    follow_up_date = followup.follow_up_date
    if isinstance(follow_up_date, str):
        follow_up_date = parse_date(follow_up_date)
    days_until = (
        (follow_up_date - timezone.localdate()).days
        if follow_up_date else 0
    )
    if days_until > 1:
        countdown = f'in {days_until} days'
    elif days_until == 1:
        countdown = 'tomorrow'
    elif days_until == 0:
        countdown = 'today'
    else:
        elapsed = abs(days_until)
        countdown = f'{elapsed} day ago' if elapsed == 1 else f'{elapsed} days ago'

    date_str = str(followup.follow_up_date)
    if followup.follow_up_end_date and followup.follow_up_end_date != followup.follow_up_date:
        date_str = f"{followup.follow_up_date} to {followup.follow_up_end_date}"

    notification_user = get_follow_up_owner(appointment)

    if notification_user:
        action_text = 'updated' if event == 'updated' else 'scheduled'
        create_notification(
            user=notification_user,
            title=f'Follow-up {action_text.title()} for {appointment.pet_name}',
            message=(
                f'A follow-up visit has been {action_text} for {appointment.pet_name} '
                f'for {date_str}, which is {countdown}. '
                f'Reason: {follow_up_reason or "Routine follow-up"}'
            ),
            notification_type=Notification.NotificationType.FOLLOW_UP,
            module_context=Notification.ModuleContext.APPOINTMENTS,
            related_object_id=appointment.id,
            related_follow_up=followup,
        )

    from notifications.followup_email_service import send_follow_up_email

    transaction.on_commit(lambda: send_follow_up_email(followup, event=event))


@transaction.atomic
def notify_medical_record_follow_up(record, actor=None):
    """Synchronize and notify a follow-up date saved on a medical record."""
    from notifications.models import FollowUp
    from notifications.followup_email_service import send_follow_up_email
    from records.models import RecordEntry

    latest_entry = RecordEntry.objects.filter(
        record=record,
    ).select_related('appointment').order_by(
        '-date_recorded', '-created_at',
    ).first()
    appointment = latest_entry.appointment if latest_entry else None
    record_followup = FollowUp.objects.filter(medical_record=record).first()
    appointment_followup = (
        FollowUp.objects.filter(appointment=appointment).order_by(
            '-created_at',
        ).first()
        if appointment else None
    )

    if not record.ff_up:
        if record_followup:
            record_followup.delete()
        if appointment_followup and appointment_followup.medical_record_id in (
            None, record.pk,
        ) and (
            not record_followup or appointment_followup.pk != record_followup.pk
        ):
            appointment_followup.delete()
        return None

    if appointment_followup and appointment_followup.medical_record_id not in (
        None, record.pk,
    ):
        appointment_followup = None

    followup = appointment_followup or record_followup
    created = followup is None
    if created:
        followup = FollowUp(
            pet_name=record.pet.name,
            follow_up_date=record.ff_up,
            reason='Medical record follow-up',
            created_by=actor,
        )

    if record_followup and record_followup.pk != followup.pk:
        record_followup.delete()

    date_changed = followup.follow_up_date != record.ff_up
    update_fields = []
    if followup.pet_name != record.pet.name:
        followup.pet_name = record.pet.name
        update_fields.append('pet_name')
    if appointment and followup.appointment_id != appointment.pk:
        followup.appointment = appointment
        update_fields.append('appointment')
    if followup.medical_record_id != record.pk:
        followup.medical_record = record
        update_fields.append('medical_record')
    if date_changed:
        followup.follow_up_date = record.ff_up
        if followup.follow_up_end_date and followup.follow_up_end_date < record.ff_up:
            followup.follow_up_end_date = None
        followup.email_sent_at = None
        followup.reminder_email_sent_at = None
        followup.email_attempts = 0
        followup.email_last_error = ''
        update_fields.extend([
            'follow_up_date', 'email_sent_at', 'reminder_email_sent_at',
            'email_attempts', 'email_last_error',
        ])
    if created:
        followup.save()
    elif update_fields:
        followup.save(update_fields=list(dict.fromkeys(update_fields)))

    if latest_entry and latest_entry.ff_up != record.ff_up:
        latest_entry.ff_up = record.ff_up
        latest_entry.save(update_fields=['ff_up', 'updated_at'])

    owner = record.pet.owner
    if owner:
        date_text = record.ff_up.strftime('%B %d, %Y')
        create_notification(
            user=owner,
            title=f'Follow-up Scheduled for {record.pet.name}',
            message=(
                f'A follow-up visit for {record.pet.name} has been scheduled for '
                f'{date_text}.'
            ),
            notification_type=Notification.NotificationType.FOLLOW_UP,
            module_context=Notification.ModuleContext.MEDICAL_RECORDS,
            related_object_id=record.id,
            related_follow_up=followup,
        )

    event = 'updated' if date_changed else 'scheduled'
    transaction.on_commit(lambda: send_follow_up_email(followup, event=event))
    return followup


@transaction.atomic
def sync_medical_record_entry_follow_up(entry, actor=None):
    """Sync a visit's follow-up to its appointment and the current record summary."""
    from notifications.models import FollowUp
    from records.models import RecordEntry

    record = entry.record
    latest_entry = RecordEntry.objects.filter(
        record=record,
    ).order_by('-date_recorded', '-created_at').first()
    if latest_entry and latest_entry.pk == entry.pk:
        record.ff_up = entry.ff_up
        record.save(update_fields=['ff_up', 'updated_at'])
        return notify_medical_record_follow_up(record, actor)

    appointment = entry.appointment
    if not appointment:
        return None

    followup = FollowUp.objects.filter(
        appointment=appointment,
    ).order_by('-created_at').first()
    if followup and followup.medical_record_id == record.pk:
        return followup
    if not entry.ff_up:
        if followup:
            followup.delete()
        return None

    event = 'updated' if followup else 'scheduled'
    if not followup:
        followup = FollowUp.objects.create(
            appointment=appointment,
            pet_name=record.pet.name,
            follow_up_date=entry.ff_up,
            reason='Medical record follow-up',
            created_by=actor,
        )
    else:
        date_changed = followup.follow_up_date != entry.ff_up
        followup.pet_name = record.pet.name
        followup.follow_up_date = entry.ff_up
        if date_changed:
            followup.email_sent_at = None
            followup.reminder_email_sent_at = None
            followup.email_attempts = 0
            followup.email_last_error = ''
        followup.save()

    notify_follow_up_scheduled(
        appointment=appointment,
        followup=followup,
        follow_up_reason=followup.reason,
        event=event,
    )
    return followup


@transaction.atomic
def sync_appointment_follow_up_to_medical_record(appointment, followup):
    """Copy an appointment follow-up to its latest linked medical-record visit."""
    from notifications.models import FollowUp
    from records.models import RecordEntry

    entry = RecordEntry.objects.filter(
        appointment=appointment,
    ).select_related('record').order_by(
        '-date_recorded', '-created_at',
    ).first()
    if not entry:
        return None

    entry.ff_up = followup.follow_up_date
    entry.save(update_fields=['ff_up', 'updated_at'])

    record = entry.record
    latest_entry = RecordEntry.objects.filter(
        record=record,
    ).order_by('-date_recorded', '-created_at').first()
    if not latest_entry or latest_entry.pk != entry.pk:
        return record

    record.ff_up = followup.follow_up_date
    record.save(update_fields=['ff_up', 'updated_at'])

    if followup.medical_record_id not in (None, record.pk):
        return record

    FollowUp.objects.filter(medical_record=record).exclude(
        pk=followup.pk,
    ).delete()
    if followup.medical_record_id != record.pk:
        followup.medical_record = record
        followup.save(update_fields=['medical_record'])
    return record


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


def notify_reservation_status(
    reservation, *, title, message, notification_type,
    notify_owner=True, notify_staff=True,
):
    """Notify the owner and inventory-enabled staff about a reservation event."""
    if notify_owner:
        create_notification(
            user=reservation.user,
            title=title,
            message=message,
            notification_type=notification_type,
            module_context=Notification.ModuleContext.INVENTORY,
            related_object_id=reservation.id,
        )
    if notify_staff:
        notify_module_users(
            module_code='reservations',
            branch=reservation.product.branch,
            title=title,
            message=message,
            notification_type=notification_type,
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
