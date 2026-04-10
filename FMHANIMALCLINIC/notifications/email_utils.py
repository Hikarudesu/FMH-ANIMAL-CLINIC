"""Utility functions for sending automated emails."""
import logging

from django.core.mail import send_mail
from django.conf import settings

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
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[appointment.owner_email],
                fail_silently=True,
            )
            return True
        except Exception as e:
            logger.warning("Failed to send appointment confirmation email to %s: %s", appointment.owner_email, e)
    return False


def send_appointment_reminder(appointment):
    """Sends a reminder email for an upcoming appointment."""
    subject = f'Reminder: Upcoming Appointment - FMH Animal Clinic ({appointment.pet_name})'

    message = f"""
    Dear {appointment.owner_name},
    
    This is a friendly reminder of your upcoming appointment for {appointment.pet_name} tomorrow.
    
    Details:
    - Date: {appointment.appointment_date.strftime('%B %d, %Y')}
    - Time: {appointment.appointment_time.strftime('%I:%M %p')}
    - Branch: {appointment.branch.name}
    
    We look forward to seeing you.
    
    Thank you,
    FMH Animal Clinic
    """

    if appointment.owner_email:
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[appointment.owner_email],
                fail_silently=True,
            )
            return True
        except Exception as e:
            logger.warning("Failed to send appointment reminder email to %s: %s", appointment.owner_email, e)
    return False


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
    
    """
    if reservation.status == 'CONFIRMED':
        message += "Thank you for picking up your reserved item(s)."
    elif reservation.status == 'CANCELLED':
        message += "This reservation is now cancelled."
    else:
        message += "We have received your reservation request and it is pending confirmation."

    message += "\n\nThank you,\nFMH Animal Clinic"

    if reservation.user.email:
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[reservation.user.email],
                fail_silently=True,
            )
            return True
        except Exception as e:
            logger.warning("Failed to send reservation notification email to %s: %s", reservation.user.email, e)
    return False
