"""
Utility functions for the appointments app.
"""
from datetime import date as _date_cls


def _parse_dob(dob_str):
    """
    Try to parse a date-of-birth string in ISO format (YYYY-MM-DD).
    Returns a date object or None if the string is empty / not parseable.
    """
    if not dob_str:
        return None
    try:
        return _date_cls.fromisoformat(str(dob_str).strip())
    except (ValueError, TypeError):
        return None


def _apply_pet_fields(pet, appointment, include_owner_fields=False):
    """
    Push the latest appointment data onto an existing Pet instance and save.
    Only updates fields that have a non-empty value in the appointment so that
    manually-entered data in the patient record is not accidentally blanked out.
    """
    changed = []

    def _set(field, value):
        if value and getattr(pet, field) != value:
            setattr(pet, field, value)
            changed.append(field)

    _set('name', (appointment.pet_name or '').strip() or None)
    _set('species', (appointment.pet_species or '').strip() or None)
    _set('breed', (appointment.pet_breed or '').strip() or None)
    _set('color', (appointment.pet_color or '').strip() or None)

    parsed_dob = _parse_dob(appointment.pet_dob)
    if parsed_dob and pet.date_of_birth != parsed_dob:
        pet.date_of_birth = parsed_dob
        changed.append('date_of_birth')

    if appointment.pet_sex and pet.sex != appointment.pet_sex:
        pet.sex = appointment.pet_sex
        changed.append('sex')

    if include_owner_fields:
        _set('guest_owner_name', (appointment.owner_name or '').strip() or None)
        _set('guest_owner_phone', (appointment.owner_phone or '').strip() or None)
        _set('guest_owner_email', (appointment.owner_email or '').strip() or None)
        _set('guest_owner_address', (appointment.owner_address or '').strip() or None)

    if changed:
        pet.save(update_fields=changed)


def sync_pet_from_appointment(appointment):
    """
    Ensures a Patient (Pet) record exists for this appointment, links it back
    via the appointment.pet FK, and keeps the Pet's fields up-to-date with the
    latest appointment data.

    Rules:
    - If appointment.pet is already linked → UPDATE that Pet with latest data
      so edits to the appointment are reflected in the patient record (and
      therefore in any linked Medical Records).
    - Portal appointment (appointment.user is set):
        Find an existing Pet for that user by name (case-insensitive).
        If none found → create one with source=PORTAL.
    - Walk-in appointment (no user):
        Find an existing walk-in Pet by name + guest owner name.
        If none found → create one with source=WALKIN using the owner/pet
        plain-text fields stored on the appointment.

    In all cases appointment.pet FK is saved and the Pet is returned.
    Returns None if there is no pet name to work with.
    """
    from patients.models import Pet

    pet_name = (appointment.pet_name or '').strip()
    if not pet_name:
        return None

    # ── Already linked: update the linked Pet and return ─────────────────────
    if appointment.pet_id:
        pet = appointment.pet
        is_walkin = not appointment.user
        _apply_pet_fields(pet, appointment, include_owner_fields=is_walkin)
        return pet

    # ── No link yet: find or create the Pet ──────────────────────────────────
    pet = None

    if appointment.user:
        # Portal user — match by owner + name
        pet = Pet.objects.filter(
            owner=appointment.user,
            name__iexact=pet_name,
        ).first()

        if not pet:
            pet = Pet.objects.create(
                owner=appointment.user,
                source=Pet.Source.PORTAL,
                name=pet_name,
                species=(appointment.pet_species or 'Unknown').strip(),
                breed=(appointment.pet_breed or '').strip(),
                date_of_birth=_parse_dob(appointment.pet_dob),
                sex=appointment.pet_sex or Pet.Sex.MALE,
                color=(appointment.pet_color or '').strip(),
            )
        else:
            # Found an existing pet — still update its details
            _apply_pet_fields(pet, appointment, include_owner_fields=False)

    else:
        # Walk-in / public booking — match by name + guest owner name
        guest_name = (appointment.owner_name or '').strip()

        pet = Pet.objects.filter(
            source=Pet.Source.WALKIN,
            name__iexact=pet_name,
            guest_owner_name__iexact=guest_name,
        ).first()

        if not pet:
            pet = Pet.objects.create(
                owner=None,
                source=Pet.Source.WALKIN,
                name=pet_name,
                species=(appointment.pet_species or 'Unknown').strip(),
                breed=(appointment.pet_breed or '').strip(),
                date_of_birth=_parse_dob(appointment.pet_dob),
                sex=appointment.pet_sex or Pet.Sex.MALE,
                color=(appointment.pet_color or '').strip(),
                guest_owner_name=guest_name,
                guest_owner_phone=(appointment.owner_phone or '').strip(),
                guest_owner_email=(appointment.owner_email or '').strip(),
                guest_owner_address=(appointment.owner_address or '').strip(),
            )
        else:
            # Found existing walk-in pet — update all fields including owner info
            _apply_pet_fields(pet, appointment, include_owner_fields=True)

    if pet:
        appointment.pet = pet
        appointment.save(update_fields=['pet'])

    return pet
