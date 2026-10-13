"""Branch-change side effects for staff accounts."""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounts.rbac_models import SpecialPermissionCodes
from appointments.models import Appointment
from notifications.delivery import send_notification_email
from notifications.models import Notification
from notifications.utils import create_notification, get_follow_up_owner

from .models import RecurringSchedule, StaffMember, VetSchedule


def _move_future_schedules(staff, old_branch_id, new_branch):
    today = timezone.localdate()
    future_schedules = VetSchedule.objects.filter(
        staff=staff,
        branch_id=old_branch_id,
        date__gte=today,
    )
    for schedule in future_schedules:
        duplicate = VetSchedule.objects.filter(
            staff=staff,
            branch=new_branch,
            date=schedule.date,
            start_time=schedule.start_time,
        ).exclude(pk=schedule.pk).exists()
        if duplicate:
            schedule.delete()
        else:
            schedule.branch = new_branch
            schedule.save(update_fields=['branch'])

    active_recurring = RecurringSchedule.objects.filter(
        staff=staff,
        branch_id=old_branch_id,
        is_active=True,
    ).filter(
        Q(effective_until__isnull=True) | Q(effective_until__gte=today),
    )
    for schedule in active_recurring:
        duplicate = RecurringSchedule.objects.filter(
            staff=staff,
            branch=new_branch,
            day_of_week=schedule.day_of_week,
            start_time=schedule.start_time,
            end_time=schedule.end_time,
            shift_type=schedule.shift_type,
            is_active=True,
            effective_from=schedule.effective_from,
            effective_until=schedule.effective_until,
        ).exclude(pk=schedule.pk).exists()
        if duplicate:
            schedule.delete()
        else:
            schedule.branch = new_branch
            schedule.save(update_fields=['branch'])


def _available_replacement(appointment, former_vet_id):
    scheduled_staff_ids = VetSchedule.objects.filter(
        branch=appointment.branch,
        date=appointment.appointment_date,
        is_available=True,
        start_time__lte=appointment.appointment_time,
        end_time__gt=appointment.appointment_time,
    ).values_list('staff_id', flat=True).distinct()

    for role_code in ('veterinarian', 'assistant_veterinarian'):
        candidates = StaffMember.objects.filter(
            pk__in=scheduled_staff_ids,
            branch=appointment.branch,
            is_active=True,
            user__is_active=True,
            user__assigned_role__code=role_code,
        ).exclude(pk=former_vet_id).select_related('user').order_by('pk')
        for candidate in candidates:
            is_booked = Appointment.objects.filter(
                preferred_vet=candidate,
                appointment_date=appointment.appointment_date,
                appointment_time=appointment.appointment_time,
                status__in=(Appointment.Status.PENDING, Appointment.Status.CONFIRMED),
            ).exclude(pk=appointment.pk).exists()
            if not is_booked:
                return candidate
    return None


def _notify_appointment_owner(appointment, former_vet_name, replacement):
    owner = get_follow_up_owner(appointment)
    branch_name = appointment.branch.name
    appointment_when = (
        f"{appointment.appointment_date.strftime('%B %d, %Y')} at "
        f"{appointment.appointment_time.strftime('%I:%M %p')}"
    )
    if replacement:
        update = f'Your appointment is now assigned to {replacement.full_name}.'
    else:
        update = (
            'We could not assign a replacement veterinarian yet. The clinic will contact you '
            'about coverage for your appointment.'
        )
    message = (
        f'Your preferred veterinarian, {former_vet_name}, has temporarily changed branches. '
        f'{update} Your appointment remains at {branch_name} on {appointment_when}; '
        'the date and time have not changed.'
    )

    if owner:
        create_notification(
            user=owner,
            title=f'Preferred veterinarian changed for {appointment.pet_name}',
            message=message,
            notification_type=Notification.NotificationType.APPOINTMENT_RESCHEDULED,
            module_context=Notification.ModuleContext.APPOINTMENTS,
            related_object_id=appointment.pk,
        )

    recipient = (getattr(owner, 'email', '') or appointment.owner_email or '').strip()
    if recipient:
        subject = f'Update to {appointment.pet_name}\'s preferred veterinarian'
        transaction.on_commit(
            lambda recipient=recipient, message=message, subject=subject: send_notification_email(
                subject=subject,
                message=message,
                recipient_list=[recipient],
                fail_silently=True,
            )
        )


def _reassign_upcoming_appointments(staff, new_branch_id):
    if not staff.user_id or not staff.user.assigned_role:
        return 0
    if staff.user.assigned_role.code not in ('veterinarian', 'assistant_veterinarian'):
        return 0

    today = timezone.localdate()
    appointments = Appointment.objects.filter(
        preferred_vet=staff,
        appointment_date__gte=today,
        status__in=(Appointment.Status.PENDING, Appointment.Status.CONFIRMED),
    ).select_related('branch', 'user', 'pet', 'preferred_vet').order_by(
        'appointment_date', 'appointment_time', 'pk',
    )
    changed = 0
    for appointment in appointments:
        former_vet_name = staff.full_name
        replacement = _available_replacement(appointment, staff.pk)
        appointment.preferred_vet = replacement
        appointment.save(update_fields=['preferred_vet', 'updated_at'])
        _notify_appointment_owner(appointment, former_vet_name, replacement)
        changed += 1
    return changed


@transaction.atomic
def apply_staff_branch_change(user, old_branch_id, new_branch):
    """Sync a changed account branch to its staff profile and dependent records."""
    new_branch_id = new_branch.pk if new_branch else None
    if old_branch_id == new_branch_id:
        return {'schedules_moved': 0, 'appointments_reassigned': 0}

    staff = StaffMember.objects.filter(user=user).first()
    if staff is None:
        return {'schedules_moved': 0, 'appointments_reassigned': 0}

    staff.branch = new_branch
    staff.save(update_fields=['branch'])

    schedules_moved = 0
    if (
        old_branch_id
        and new_branch
        and user.has_role_special_permission(SpecialPermissionCodes.MANAGE_OWN_SCHEDULE)
    ):
        before_count = VetSchedule.objects.filter(
            staff=staff,
            branch_id=old_branch_id,
            date__gte=timezone.localdate(),
        ).count()
        recurring_count = RecurringSchedule.objects.filter(
            staff=staff,
            branch_id=old_branch_id,
            is_active=True,
        ).count()
        _move_future_schedules(staff, old_branch_id, new_branch)
        schedules_moved = before_count + recurring_count

    appointments_reassigned = _reassign_upcoming_appointments(staff, new_branch_id)
    return {
        'schedules_moved': schedules_moved,
        'appointments_reassigned': appointments_reassigned,
    }