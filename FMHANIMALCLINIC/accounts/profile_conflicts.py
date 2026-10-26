"""Shared duplicate checks for profile name and email fields."""
from django.db.models.functions import Trim

from .models import User


def find_profile_conflicts(*, user, first_name='', last_name='', email=''):
    """Return whether another account or guest record uses the submitted details."""
    other_users = User.objects.exclude(pk=user.pk)
    normalized_first_name = first_name.strip()
    normalized_last_name = last_name.strip()
    normalized_email = email.strip()

    name_exists = False
    if normalized_first_name and normalized_last_name:
        name_exists = other_users.annotate(
            normalized_first_name=Trim('first_name'),
            normalized_last_name=Trim('last_name'),
        ).filter(
            normalized_first_name__iexact=normalized_first_name,
            normalized_last_name__iexact=normalized_last_name,
        ).exists()

    email_exists = bool(
        normalized_email
        and other_users.filter(email__iexact=normalized_email).exists()
    )
    guest_email_exists = False
    if normalized_email:
        from appointments.models import Appointment
        from patients.models import Pet

        guest_email_exists = (
            Pet.objects.filter(
                source=Pet.Source.WALKIN,
                guest_owner_email__iexact=normalized_email,
            ).exists()
            or Appointment.objects.filter(
                source=Appointment.Source.WALKIN,
                owner_email__iexact=normalized_email,
            ).exists()
        )

    return {
        'name_exists': name_exists,
        'email_exists': email_exists or guest_email_exists,
        'guest_email_exists': guest_email_exists,
    }
