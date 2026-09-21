"""Signal handlers for medical file lifecycle cleanup."""

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from utils.file_cleanup import safely_delete_field_file

from .models import MedicalFile


@receiver(pre_save, sender=MedicalFile)
def stash_old_medical_file(sender, instance, **kwargs):
    """Cache the previous file so replaced uploads can be removed on save."""
    instance._old_file = None  # pylint: disable=protected-access
    if not instance.pk:
        return

    try:
        old_instance = MedicalFile.objects.only('file').get(pk=instance.pk)
    except MedicalFile.DoesNotExist:
        return

    old_name = old_instance.file.name if old_instance.file else ''
    new_name = instance.file.name if instance.file else ''
    if old_name and old_name != new_name:
        instance._old_file = old_instance.file  # pylint: disable=protected-access


@receiver(post_save, sender=MedicalFile)
def cleanup_replaced_medical_file(sender, instance, **kwargs):
    """Remove replaced medical file after successful save."""
    old_file = getattr(instance, '_old_file', None)
    if old_file:
        safely_delete_field_file(old_file)


@receiver(post_delete, sender=MedicalFile)
def cleanup_deleted_medical_file(sender, instance, **kwargs):
    """Delete medical file from storage when the record is removed."""
    safely_delete_field_file(instance.file)
