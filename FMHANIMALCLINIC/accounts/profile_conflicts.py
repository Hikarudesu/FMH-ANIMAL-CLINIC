"""Shared duplicate checks for profile name and email fields."""
from django.db.models.functions import Trim

from .models import User


def find_profile_conflicts(*, user, first_name='', last_name='', email=''):
    """Return whether another account already uses the submitted name or email."""
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
    return {
        'name_exists': name_exists,
        'email_exists': email_exists,
    }
