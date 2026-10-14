"""Keep a pet owner's current clinical and scheduling data with their branch."""

from django.db.models import Q

from appointments.models import Appointment
from patients.models import Pet
from records.models import MedicalRecord


def sync_owner_branch_data(user, branch):
    """Move the owner's pets, medical records, and appointments to a branch."""
    Pet.all_objects.filter(owner=user).update(branch=branch)
    MedicalRecord.all_objects.filter(pet__owner=user).update(branch=branch)
    Appointment.objects.filter(
        Q(user=user) | Q(pet__owner=user)
    ).update(branch=branch)