"""
Models for managing Patient Medical Records.
"""
import hashlib
import os
import subprocess
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
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


def medical_file_upload_path(instance, filename):
    extension = os.path.splitext(filename)[1].lower()
    return f'medical/{instance.record.pet_id}/{uuid.uuid4().hex}{extension}'


def validate_medical_file(upload):
    if upload.size > 20 * 1024 * 1024:
        raise ValidationError('Medical files must not exceed 20 MB.')
    extension = os.path.splitext(upload.name)[1].lower()
    allowed = {'.pdf', '.png', '.jpg', '.jpeg', '.doc', '.docx', '.xls', '.xlsx'}
    if extension not in allowed:
        raise ValidationError('Unsupported medical file type.')
    header = upload.read(16)
    upload.seek(0)
    signatures = {
        '.pdf': header.startswith(b'%PDF-'),
        '.png': header.startswith(b'\x89PNG\r\n\x1a\n'),
        '.jpg': header.startswith(b'\xff\xd8\xff'),
        '.jpeg': header.startswith(b'\xff\xd8\xff'),
        '.doc': header.startswith(b'\xd0\xcf\x11\xe0'),
        '.xls': header.startswith(b'\xd0\xcf\x11\xe0'),
        '.docx': header.startswith(b'PK\x03\x04'),
        '.xlsx': header.startswith(b'PK\x03\x04'),
    }
    if not signatures[extension]:
        raise ValidationError('The file content does not match its extension.')
    if getattr(settings, 'CLAMAV_ENABLED', False):
        try:
            result = subprocess.run(
                ['clamdscan', '--no-summary', '-'], input=upload.read(),
                capture_output=True, check=False, timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            if getattr(settings, 'CLAMAV_REQUIRED', not settings.DEBUG):
                raise ValidationError('Malware scanning is unavailable.') from exc
        else:
            if result.returncode != 0:
                raise ValidationError('The uploaded file failed malware scanning.')
    upload.seek(0)


class MedicalFile(models.Model):
    """Private laboratory, imaging, and external medical document."""
    class FileType(models.TextChoices):
        LAB = 'LAB', 'Laboratory Result'
        IMAGING = 'IMAGING', 'Medical Imaging'
        OTHER = 'OTHER', 'Other Medical Document'

    record = models.ForeignKey(MedicalRecord, on_delete=models.CASCADE, related_name='medical_files')
    file = models.FileField(upload_to=medical_file_upload_path, validators=[validate_medical_file])
    original_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=20, choices=FileType.choices, default=FileType.OTHER)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    sha256 = models.CharField(max_length=64, editable=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def save(self, *args, **kwargs):
        if self.file and not self.sha256:
            digest = hashlib.sha256()
            for chunk in self.file.chunks():
                digest.update(chunk)
            self.sha256 = digest.hexdigest()
            self.file.seek(0)
        self.original_name = self.original_name or os.path.basename(self.file.name)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Delete the stored file from storage before deleting the DB row."""
        if self.file:
            try:
                self.file.delete(save=False)
            except Exception:
                pass
        return super().delete(*args, **kwargs)


class MedicalFileAccessLog(models.Model):
    """Immutable audit trail for medical-file access attempts."""
    class Action(models.TextChoices):
        UPLOAD = 'UPLOAD', 'Upload'
        DOWNLOAD = 'DOWNLOAD', 'Download'
        DELETE = 'DELETE', 'Delete'
        DENIED = 'DENIED', 'Denied'

    medical_file = models.ForeignKey(MedicalFile, on_delete=models.SET_NULL, null=True, related_name='access_logs')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=20, choices=Action.choices)
    success = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    detail = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['medical_file', 'created_at'])]


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

    try:
        pet = instance.record.pet
    except Exception:
        return

    try:
        clinical_status_obj = instance.action_required
        if clinical_status_obj is None:
            clinical_status_obj = ClinicalStatus.get_default()
            instance.action_required = clinical_status_obj
            instance.save(update_fields=['action_required'])
    except Exception:
        return

    try:
        new_status_code = clinical_status_obj.code
        old_status_code = pet.clinical_status.code if pet.clinical_status else None
        if old_status_code == new_status_code:
            return

        pet.clinical_status = clinical_status_obj
        pet.save(update_fields=['clinical_status'])
    except Exception:
        return

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

    # Also notify vet assistants in the same branch (they have medical records access)
    if instance.record.branch:
        from accounts.models import User
        from notifications.models import Notification

        vet_assistants = User.objects.filter(
            is_active=True,
            assigned_role__code='assistant_veterinarian',
            branch=instance.record.branch,
        )
        
        for vet_assistant in vet_assistants:
            status_msg = STATUS_MESSAGES.get(new_status_code, 'has an updated clinical status.')
            Notification.objects.create(
                user=vet_assistant,
                title=f"Clinical Status Update: {pet.name}",
                message=f"{pet.name}'s clinical status has changed to: {clinical_status_obj.description}. {status_msg}",
                notification_type=Notification.NotificationType.MEDICAL_RECORD_UPDATE,
                module_context=Notification.ModuleContext.MEDICAL_RECORDS,
                related_object_id=instance.record.id,
            )
        
        # Also notify veterinarians in the same branch
        veterinarians = User.objects.filter(
            is_active=True,
            assigned_role__code='veterinarian',
            branch=instance.record.branch,
        )
        
        for veterinarian in veterinarians:
            status_msg = STATUS_MESSAGES.get(new_status_code, 'has an updated clinical status.')
            Notification.objects.create(
                user=veterinarian,
                title=f"Clinical Status Update: {pet.name}",
                message=f"{pet.name}'s clinical status has changed to: {clinical_status_obj.description}. {status_msg}",
                notification_type=Notification.NotificationType.MEDICAL_RECORD_UPDATE,
                module_context=Notification.ModuleContext.MEDICAL_RECORDS,
                related_object_id=instance.record.id,
            )

