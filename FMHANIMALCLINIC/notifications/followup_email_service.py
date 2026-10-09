"""Idempotent email delivery for scheduled follow-up visits."""
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.conf import settings

from .delivery import send_notification_email
from .utils import get_follow_up_owner


def _follow_up_recipient(follow_up):
    """Return the best available email for a registered or guest owner."""
    appointment = follow_up.appointment
    owner = get_follow_up_owner(appointment)
    return (
        (owner.email if owner else '')
        or (appointment.owner_email if appointment else '')
        or (
            follow_up.medical_record.pet.owner.email
            if follow_up.medical_record_id
            and follow_up.medical_record.pet.owner_id
            else ''
        )
    ).strip().lower()


def send_follow_up_email(follow_up, event='scheduled'):
    appointment = follow_up.appointment
    pet = follow_up.medical_record.pet if follow_up.medical_record_id else None
    owner = get_follow_up_owner(appointment) or (pet.owner if pet and pet.owner_id else None)
    recipient = _follow_up_recipient(follow_up)
    if follow_up.email_sent_at:
        return True, 'Already sent.'
    if not recipient:
        follow_up.email_attempts += 1
        follow_up.email_last_error = 'Appointment or registered pet owner has no email address.'
        follow_up.save(update_fields=['email_attempts', 'email_last_error'])
        return False, follow_up.email_last_error

    date_text = str(follow_up.follow_up_date)
    follow_up_date = follow_up.follow_up_date
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
    if follow_up.follow_up_end_date and follow_up.follow_up_end_date != follow_up.follow_up_date:
        date_text = f'{follow_up.follow_up_date} to {follow_up.follow_up_end_date}'
    try:
        sent = send_notification_email(
            subject=(
                f'Follow-up {"Updated" if event == "updated" else "Scheduled"} '
                f'- FMH Animal Clinic ({follow_up.pet_name})'
            ),
            message=(
                f'Dear {(appointment.owner_name if appointment else owner.get_full_name() if owner else "Pet Owner")},\n\n'
                f'Your follow-up visit for {follow_up.pet_name} has been '
                f'{"updated" if event == "updated" else "scheduled"} for {date_text} '
                f'({countdown}).\n'
                f'Reason: {follow_up.reason or "Routine follow-up"}.\n\n'
                'Please contact FMH Animal Clinic if you need to reschedule.\n'
            ),
            recipient_list=[recipient],
            fail_silently=False,
            from_email=settings.DEFAULT_FROM_EMAIL,
            force=True,
        )
    except Exception as exc:
        sent = False
        follow_up.email_last_error = str(exc)
    if sent:
        follow_up.email_sent_at = timezone.now()
        follow_up.email_last_error = ''
        follow_up.save(update_fields=['email_sent_at', 'email_last_error'])
        return True, 'Sent.'

    follow_up.email_attempts += 1
    follow_up.email_last_error = follow_up.email_last_error or 'Email backend did not accept the message.'
    follow_up.save(update_fields=['email_attempts', 'email_last_error'])
    return False, follow_up.email_last_error


def send_follow_up_reminder_email(follow_up):
    """Send the separate reminder email scheduled three days before a visit."""
    appointment = follow_up.appointment
    pet = follow_up.medical_record.pet if follow_up.medical_record_id else None
    owner = get_follow_up_owner(appointment) or (pet.owner if pet and pet.owner_id else None)
    recipient = _follow_up_recipient(follow_up)
    if follow_up.reminder_email_sent_at:
        return True, 'Already sent.'
    if not recipient:
        return False, 'Pet owner has no email address.'

    date_text = str(follow_up.follow_up_date)
    follow_up_date = follow_up.follow_up_date
    if isinstance(follow_up_date, str):
        follow_up_date = parse_date(follow_up_date)
    days_until = (
        (follow_up_date - timezone.localdate()).days
        if follow_up_date else 0
    )
    if follow_up.follow_up_end_date and follow_up.follow_up_end_date != follow_up.follow_up_date:
        date_text = f'{follow_up.follow_up_date} to {follow_up.follow_up_end_date}'
    try:
        sent = send_notification_email(
            subject=f'Follow-up Reminder in 3 Days - FMH Animal Clinic ({follow_up.pet_name})',
            message=(
                f'Dear {(appointment.owner_name if appointment else owner.get_full_name() if owner else "Pet Owner")},\n\n'
                f'This is your 3-day reminder: {follow_up.pet_name} has a follow-up visit '
                f'scheduled for {date_text} (in {days_until} days).\n'
                f'Reason: {follow_up.reason or "Routine follow-up"}.\n\n'
                'Please contact FMH Animal Clinic if you need to reschedule.\n'
            ),
            recipient_list=[recipient],
            fail_silently=False,
            from_email=settings.DEFAULT_FROM_EMAIL,
            force=True,
        )
    except Exception as exc:
        follow_up.email_last_error = str(exc)
        sent = False
    if sent:
        follow_up.reminder_email_sent_at = timezone.now()
        follow_up.email_last_error = ''
        follow_up.save(update_fields=['reminder_email_sent_at', 'email_last_error'])
        return True, 'Sent.'

    follow_up.email_attempts += 1
    follow_up.email_last_error = follow_up.email_last_error or 'Email backend did not accept the message.'
    follow_up.save(update_fields=['email_attempts', 'email_last_error'])
    return False, follow_up.email_last_error