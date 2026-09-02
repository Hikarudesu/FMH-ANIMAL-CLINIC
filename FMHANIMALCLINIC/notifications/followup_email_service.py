"""Idempotent email delivery for scheduled follow-up visits."""
from django.utils import timezone

from .delivery import send_notification_email


def send_follow_up_email(follow_up):
    appointment = follow_up.appointment
    recipient = (appointment.owner_email or '').strip().lower()
    if follow_up.email_sent_at:
        return True, 'Already sent.'
    if not recipient:
        follow_up.email_attempts += 1
        follow_up.email_last_error = 'Appointment owner has no email address.'
        follow_up.save(update_fields=['email_attempts', 'email_last_error'])
        return False, follow_up.email_last_error

    date_text = str(follow_up.follow_up_date)
    if follow_up.follow_up_end_date and follow_up.follow_up_end_date != follow_up.follow_up_date:
        date_text = f'{follow_up.follow_up_date} to {follow_up.follow_up_end_date}'
    try:
        sent = send_notification_email(
            subject=f'Follow-up Reminder - FMH Animal Clinic ({follow_up.pet_name})',
            message=(
                f'Dear {appointment.owner_name},\n\n'
                f'Your follow-up visit for {follow_up.pet_name} is scheduled for {date_text}.\n'
                f'Reason: {follow_up.reason or "Routine follow-up"}.\n\n'
                'Please contact FMH Animal Clinic if you need to reschedule.\n'
            ),
            recipient_list=[recipient],
            fail_silently=False,
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