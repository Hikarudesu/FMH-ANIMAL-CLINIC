"""Owner identity matching shared by guest-registration workflows."""
from django.contrib.auth import get_user_model
from django.db.models import Q


def _normalized_phone(value):
    return ''.join(character for character in (value or '') if character.isdigit())


def check_existing_owner_identity(owner_name, phone='', email=''):
    """Return whether an owner name exists and whether contact details also match."""
    normalized_name = ' '.join((owner_name or '').split()).casefold()
    normalized_phone = _normalized_phone(phone)
    normalized_email = (email or '').strip().casefold()
    User = get_user_model()

    from appointments.models import Appointment
    from patients.models import Pet

    email_match = bool(
        normalized_email
        and (
            User.objects.filter(email__iexact=normalized_email).exists()
            or Appointment.objects.filter(
                source=Appointment.Source.WALKIN,
                owner_email__iexact=normalized_email,
            ).exists()
            or Pet.objects.filter(
                source=Pet.Source.WALKIN,
                guest_owner_email__iexact=normalized_email,
            ).exists()
        )
    )
    if not normalized_name:
        return {
            'name_match': False,
            'identity_match': False,
            'email_match': email_match,
        }

    matches = []

    name_parts = normalized_name.split()
    user_name_query = Q(username__iexact=owner_name.strip())
    if len(name_parts) == 1:
        user_name_query |= (
            Q(first_name__iexact=name_parts[0])
            | Q(last_name__iexact=name_parts[0])
        )
    else:
        user_name_query |= Q(
            first_name__iexact=name_parts[0],
            last_name__iexact=' '.join(name_parts[1:]),
        )
    owners = User.objects.filter(
        Q(assigned_role__is_staff_role=False)
        | Q(assigned_role__isnull=True)
    ).filter(user_name_query).values(
        'username', 'first_name', 'last_name', 'email', 'phone_number',
    )
    for owner in owners:
        full_name = ' '.join(
            (owner['first_name'] or '', owner['last_name'] or '')
        ).strip() or owner['username']
        if ' '.join(full_name.split()).casefold() == normalized_name:
            matches.append((owner['phone_number'], owner['email']))

    appointments = Appointment.objects.filter(
        source=Appointment.Source.WALKIN,
        owner_name__iexact=owner_name.strip(),
    ).values_list('owner_phone', 'owner_email')
    matches.extend(appointments)

    guest_owners = Pet.objects.filter(
        source=Pet.Source.WALKIN,
        guest_owner_name__iexact=owner_name.strip(),
    ).values_list('guest_owner_phone', 'guest_owner_email')
    matches.extend(guest_owners)

    identity_match = any(
        (
            normalized_phone
            and _normalized_phone(existing_phone) == normalized_phone
        )
        or (
            normalized_email
            and (existing_email or '').strip().casefold() == normalized_email
        )
        for existing_phone, existing_email in matches
    )
    return {
        'name_match': bool(matches),
        'identity_match': identity_match,
        'email_match': email_match,
    }
