"""Capture appointment changes for staff and owner-facing timelines."""
from datetime import date, datetime, time

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from accounts.activity_context import get_current_actor
from branches.models import Branch
from employees.models import StaffMember
from settings.models import ReasonForVisit

from .models import Appointment, AppointmentHistory


TRACKED_FIELDS = (
    ('status', 'Status', True),
    ('owner_name', 'Owner name', False),
    ('owner_email', 'Owner email', False),
    ('owner_phone', 'Owner phone', False),
    ('owner_address', 'Owner address', False),
    ('pet_name', 'Pet name', False),
    ('pet_species', 'Species', False),
    ('pet_breed', 'Breed', False),
    ('pet_dob', 'Date of birth', False),
    ('pet_sex', 'Sex', False),
    ('pet_color', 'Color', False),
    ('pet_symptoms', 'Reported symptoms', False),
    ('appointment_date', 'Date', True),
    ('appointment_time', 'Time', True),
    ('branch_id', 'Branch', True),
    ('preferred_vet_id', 'Veterinarian', True),
    ('reason_for_visit_id', 'Reason for visit', True),
    ('source', 'Booking source', False),
    ('notes', 'Appointment notes', False),
    ('cancellation_reason', 'Cancellation reason', False),
    ('medical_record_decision', 'Medical record decision', False),
)
FIELD_MODELS = {
    'branch_id': (Branch, 'name'),
    'preferred_vet_id': (StaffMember, 'full_name'),
    'reason_for_visit_id': (ReasonForVisit, 'name'),
}
STATUS_SUMMARIES = {
    Appointment.Status.PENDING: 'Appointment request submitted',
    Appointment.Status.CONFIRMED: 'Appointment confirmed',
    Appointment.Status.CHECKED_IN: 'Checked in at the clinic',
    Appointment.Status.IN_PROGRESS: 'Consultation started',
    Appointment.Status.AWAITING_PAYMENT: 'Ready for payment',
    Appointment.Status.CANCELLED: 'Appointment cancelled',
    Appointment.Status.COMPLETED: 'Appointment completed',
}


def _actor():
    actor = get_current_actor()
    return actor if actor and actor.is_authenticated else None


def _display_value(field_name, value):
    if value is None or value == '':
        return '—'
    if field_name == 'status':
        return dict(Appointment.Status.choices).get(value, value)
    if field_name == 'medical_record_decision':
        return dict(Appointment.MedicalRecordDecision.choices).get(value, value)
    if field_name == 'source':
        return dict(Appointment.Source.choices).get(value, value)
    if field_name == 'appointment_date' and isinstance(value, date):
        return value.isoformat()
    if field_name == 'appointment_time' and isinstance(value, time):
        return value.strftime('%I:%M %p')
    if field_name in FIELD_MODELS:
        model, display_field = FIELD_MODELS[field_name]
        obj = model.objects.filter(pk=value).first()
        return getattr(obj, display_field) if obj else '—'
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _record_changes(instance, old_values, update_fields):
    changes = []
    owner_visible = False
    for field_name, label, visible_to_owner in TRACKED_FIELDS:
        if update_fields is not None and not {
            field_name,
            field_name[:-3] if field_name.endswith('_id') else field_name,
        }.intersection(update_fields):
            continue
        old_value = old_values[field_name]
        new_value = getattr(instance, field_name)
        if old_value == new_value:
            continue
        changes.append({
            'field': label,
            'from': _display_value(field_name, old_value),
            'to': _display_value(field_name, new_value),
        })
        owner_visible = owner_visible or visible_to_owner

    if not changes:
        return

    status_changed = any(change['field'] == 'Status' for change in changes)
    if status_changed:
        event_type = AppointmentHistory.EventType.STATUS_CHANGED
        summary = STATUS_SUMMARIES.get(instance.status, 'Appointment status updated')
    else:
        event_type = AppointmentHistory.EventType.UPDATED
        summary = (
            'Appointment schedule updated'
            if owner_visible else 'Appointment details updated'
        )

    AppointmentHistory.objects.create(
        appointment=instance,
        actor=_actor(),
        event_type=event_type,
        summary=summary,
        changes=changes,
        owner_visible=owner_visible,
    )


@receiver(pre_save, sender=Appointment)
def capture_appointment_previous_values(sender, instance, **kwargs):
    if not instance.pk:
        instance._history_previous_values = None
        return
    tracked_names = [field_name for field_name, _, _ in TRACKED_FIELDS]
    instance._history_previous_values = (
        Appointment.objects.filter(pk=instance.pk)
        .values(*tracked_names)
        .first()
    )


@receiver(post_save, sender=Appointment)
def record_appointment_history(sender, instance, created, update_fields, **kwargs):
    if created:
        AppointmentHistory.objects.create(
            appointment=instance,
            actor=_actor(),
            event_type=AppointmentHistory.EventType.BOOKED,
            summary=STATUS_SUMMARIES.get(
                instance.status,
                'Appointment booked',
            ),
            owner_visible=True,
        )
        return

    old_values = getattr(instance, '_history_previous_values', None)
    if old_values:
        _record_changes(instance, old_values, update_fields)
