"""
Models for managing Patient Medical Records.
"""
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from patients.models import Pet
from employees.models import StaffMember
from branches.models import Branch


class MedicalRecord(models.Model):
    """
    Represents a specific medical record/visit history item attached to a Pet.
    """
    pet = models.ForeignKey(Pet, on_delete=models.CASCADE,
                            related_name='medical_records')
    vet = models.ForeignKey(StaffMember, on_delete=models.SET_NULL,
                            null=True, blank=True, related_name='medical_records')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL,
                               null=True, blank=True,
                               related_name='medical_records')
    weight = models.DecimalField(
        max_digits=5, decimal_places=2, help_text="Weight in kg", null=True, blank=True)
    temperature = models.DecimalField(
        max_digits=4, decimal_places=1, help_text="Temperature in °C", null=True, blank=True)
    history_clinical_signs = models.TextField(
        verbose_name="History / Clinical Signs", blank=True, null=True)
    treatment = models.TextField(verbose_name="Tx (Treatment)", blank=True)
    rx = models.TextField(
        verbose_name="Rx (Prescription)", blank=True, null=True)
    lab_results = models.TextField(
        verbose_name="Lab Results", blank=True, null=True)
    ff_up = models.DateField(
        verbose_name="FF-UP (Follow-Up)", blank=True, null=True)
    date_recorded = models.DateField()

    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Inactive', 'Inactive'),
    ]
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='Active')

    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = models.Manager()

    class Meta:
        """Meta options for MedicalRecord model."""
        ordering = ['-date_recorded', '-created_at']
        indexes = [
            models.Index(fields=['pet', 'created_at']),
            models.Index(fields=['date_recorded']),
            models.Index(fields=['branch', 'date_recorded']),
        ]

    def __str__(self):
        return f"Record for {self.pet.name} on {self.date_recorded}"

    @property
    def latest_entry(self):
        """Return the most recent RecordEntry for this record."""
        return self.entries.order_by('-date_recorded', '-created_at').first()


class RecordEntry(models.Model):
    """
    Represents a single visit/consultation entry on a pet's medical record card.
    Multiple entries can belong to one MedicalRecord (one card per pet).
    """
    record = models.ForeignKey(
        MedicalRecord, on_delete=models.CASCADE, related_name='entries')
    vet = models.ForeignKey(
        StaffMember, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='record_entries')
    date_recorded = models.DateField()
    weight = models.DecimalField(
        max_digits=5, decimal_places=2, help_text="Weight in kg",
        null=True, blank=True)
    temperature = models.DecimalField(
        max_digits=4, decimal_places=1, help_text="Temperature in °C",
        null=True, blank=True)
    history_clinical_signs = models.TextField(
        verbose_name="History / Clinical Signs", blank=True, null=True)
    treatment = models.TextField(verbose_name="Tx (Treatment)", blank=True, null=True)
    rx = models.TextField(
        verbose_name="Rx (Prescription)", blank=True, null=True)
    lab_results = models.TextField(
        verbose_name="Lab Results", blank=True, null=True)
    ff_up = models.DateField(
        verbose_name="FF-UP (Follow-Up)", blank=True, null=True)
    action_required = models.ForeignKey(
        'settings.ClinicalStatus',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='record_entries_action',
        verbose_name='Required Action',
        help_text='The next step required after this consultation.',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = models.Manager()

    class Meta:
        """Meta options for RecordEntry model."""
        ordering = ['-date_recorded', '-created_at']
        indexes = [
            models.Index(fields=['record', 'date_recorded']),
            models.Index(fields=['date_recorded']),
        ]

    def __str__(self):
        return f"Entry for {self.record.pet.name} on {self.date_recorded}"


# ── Signal: auto-sync RecordEntry.action_required → Pet.clinical_status ──

# Human-friendly messages for owner notifications
STATUS_MESSAGES = {
    Pet.ClinicalStatus.HEALTHY: 'has been discharged and is doing well.',
    Pet.ClinicalStatus.MONITOR: 'has been admitted for monitoring. Our team is keeping a close eye on them.',
    Pet.ClinicalStatus.TREATMENT: 'is currently in treatment. Our team is providing the best care possible.',
    Pet.ClinicalStatus.SURGERY: 'has been admitted for surgery. We will keep you updated.',
    Pet.ClinicalStatus.DIAGNOSTICS: 'has pending diagnostics/lab work. Results will be available soon.',
    Pet.ClinicalStatus.CRITICAL: 'is in critical condition. Our team is doing everything possible.',
}


@receiver(post_save, sender=RecordEntry)
def sync_pet_clinical_status(sender, instance, **kwargs):
    """When a RecordEntry is saved, update the pet's clinical status and notify the owner if it changed."""
    from settings.models import ClinicalStatus
    from settings.utils import get_setting

    pet = instance.record.pet

    clinical_status_obj = instance.action_required
    if clinical_status_obj is None:
        clinical_status_obj = ClinicalStatus.get_default()
        instance.action_required = clinical_status_obj
        instance.save(update_fields=['action_required'])

    new_status_code = clinical_status_obj.code

    old_status_code = pet.clinical_status.code if pet.clinical_status else None
    if old_status_code == new_status_code:
        return

    pet.clinical_status = clinical_status_obj
    pet.save(update_fields=['clinical_status'])

    auto_actions_enabled = bool(get_setting('medical_clinical_status_auto_actions', True))
    if not auto_actions_enabled:
        return

    # Create a notification for the pet's owner (only if owner exists)
    if pet.owner:
        from notifications.models import Notification  # local import to avoid circular

        status_msg = STATUS_MESSAGES.get(new_status_code, 'has an updated clinical status.')
        Notification.objects.create(
            user=pet.owner,
            title=f"Clinical Update: {pet.name}",
            message=f"Your pet {pet.name} {status_msg}",
            notification_type=Notification.NotificationType.GENERAL,
            module_context=Notification.ModuleContext.MEDICAL_RECORDS,
        )

