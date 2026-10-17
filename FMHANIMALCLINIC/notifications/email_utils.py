"""Utility functions for sending automated emails."""
import logging

from .delivery import send_notification_email

logger = logging.getLogger('fmh')


def send_appointment_confirmation(appointment):
    """Sends a confirmation email when an appointment is booked."""
    subject = f'Appointment Confirmation - FMH Animal Clinic ({appointment.pet_name})'

    # We render the email content, but for simplicity we'll just use a formatted string
    # since we don't have dedicated email templates yet.
    message = f"""
    Dear {appointment.owner_name},
    
    Your appointment for {appointment.pet_name} has been successfully booked.
    
    Details:
    - Date: {appointment.appointment_date.strftime('%B %d, %Y')}
    - Time: {appointment.appointment_time.strftime('%I:%M %p')}
    - Branch: {appointment.branch.name}
    - Reason: {appointment.reason_display}
    
    Please arrive 10 minutes early. If you need to reschedule or cancel, please contact us.
    
    Thank you,
    FMH Animal Clinic
    """

    if appointment.owner_email:
        sent = send_notification_email(
            subject=subject,
            message=message,
            recipient_list=[appointment.owner_email],
            fail_silently=True,
        )
        if sent:
            return True
        logger.warning("Failed to send appointment confirmation email to %s", appointment.owner_email)
    return False


def send_appointment_reminder(appointment, reminder_num=1):
    """
    Sends a reminder email for an upcoming appointment.
    
    Args:
        appointment: The Appointment object
        reminder_num: Which reminder this is (1 or 2). Default is 1.
    """
    if reminder_num == 2:
        subject = f'Final Reminder: Appointment in 3 Hours - FMH Animal Clinic ({appointment.pet_name})'
        timing = 'in 3 hours'
        message_intro = 'This is your final reminder about your appointment scheduled'
    else:
        subject = f'Reminder: Upcoming Appointment - FMH Animal Clinic ({appointment.pet_name})'
        timing = 'tomorrow'
        message_intro = 'This is a friendly reminder of your upcoming appointment'

    message = f"""
    Dear {appointment.owner_name},
    
    {message_intro} for {appointment.pet_name} {timing}.
    
    Details:
    - Date: {appointment.appointment_date.strftime('%B %d, %Y')}
    - Time: {appointment.appointment_time.strftime('%I:%M %p')}
    - Branch: {appointment.branch.name}
    
    We look forward to seeing you.
    
    Thank you,
    FMH Animal Clinic
    """

    if appointment.owner_email:
        sent = send_notification_email(
            subject=subject,
            message=message,
            recipient_list=[appointment.owner_email],
            fail_silently=True,
        )
        if sent:
            return True
        logger.warning("Failed to send appointment reminder email to %s", appointment.owner_email)
    return False


def send_appointment_cancellation_email(appointment, actor_label):
    """Email the appointment owner when an appointment is cancelled."""
    recipient = (
        appointment.user.email
        if appointment.user and appointment.user.email
        else appointment.owner_email
    )
    if not recipient:
        return False

    subject = f'Appointment Cancelled - FMH Animal Clinic ({appointment.pet_name})'
    message = (
        f'Dear {appointment.owner_name or "Pet Owner"},\n\n'
        f'The appointment for {appointment.pet_name} scheduled on '
        f'{appointment.appointment_date.strftime("%B %d, %Y")} at '
        f'{appointment.appointment_time.strftime("%I:%M %p")} at '
        f'{appointment.branch.name if appointment.branch else "your clinic"} '
        f'was cancelled by {actor_label}.\n'
    )
    if appointment.cancellation_reason:
        message += f'\nReason: {appointment.cancellation_reason}\n'
    message += '\nIf you need help, please contact the clinic.\n\nFMH Animal Clinic'

    sent = send_notification_email(
        subject=subject,
        message=message,
        recipient_list=[recipient],
        fail_silently=True,
    )
    if not sent:
        logger.warning(
            "Failed to send appointment cancellation email to %s",
            recipient,
        )
    return sent


def send_appointment_deletion_email(appointment):
    """Email the owner when staff permanently remove a cancelled appointment."""
    recipient = (
        appointment.user.email
        if appointment.user and appointment.user.email
        else appointment.owner_email
    )
    if not recipient:
        return False

    subject = f'Cancelled Appointment Removed - FMH Animal Clinic ({appointment.pet_name})'
    message = (
        f'Dear {appointment.owner_name or "Pet Owner"},\n\n'
        f'The cancelled appointment for {appointment.pet_name} scheduled on '
        f'{appointment.appointment_date.strftime("%B %d, %Y")} at '
        f'{appointment.appointment_time.strftime("%I:%M %p")} has been '
        'removed from the clinic appointment system by clinic staff. '
        'This does not change the cancellation status of the appointment.\n'
    )
    if appointment.cancellation_reason:
        message += f'\nCancellation reason on file: {appointment.cancellation_reason}\n'
    message += '\nPlease contact the clinic if you need further information.\n\nFMH Animal Clinic'

    sent = send_notification_email(
        subject=subject,
        message=message,
        recipient_list=[recipient],
        fail_silently=True,
    )
    if not sent:
        logger.warning(
            "Failed to send appointment deletion email to %s",
            recipient,
        )
    return sent


def send_reservation_notification(reservation):
    """Sends an email when an inventory reservation status changes."""
    status = reservation.get_status_display().lower()
    subject = f'Reservation {status.title()} - FMH Animal Clinic'

    owner_name = getattr(reservation.user, 'first_name', '') or getattr(
        reservation.user, 'username', 'Customer')

    message = f"""
    Dear {owner_name},
    
    Your reservation (RSV-{reservation.pk}) has been {status}.
    
    Item: {reservation.product.name}
    Quantity: {reservation.quantity}
    Unit: {reservation.product.unit_display}
    Sale Category: {reservation.product.sale_type_label}
    
    """
    if reservation.status == 'CONFIRMED':
        message += "Thank you for picking up your reserved item(s)."
    elif reservation.status == 'CANCELLED':
        message += "This reservation is now cancelled."
    else:
        message += "We have received your reservation request and it is pending confirmation."

    message += "\n\nThank you,\nFMH Animal Clinic"

    if reservation.user.email:
        sent = send_notification_email(
            subject=subject,
            message=message,
            recipient_list=[reservation.user.email],
            fail_silently=True,
        )
        if sent:
            return True
        logger.warning("Failed to send reservation notification email to %s", reservation.user.email)
    return False
