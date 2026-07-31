"""Signal handlers for patient media lifecycle."""

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from utils.file_cleanup import safely_delete_field_file
from .models import Pet


@receiver(pre_save, sender=Pet)
def stash_old_pet_photo(sender, instance, **kwargs):
    """Track previous pet photo so replaced files can be cleaned up post-save."""
    instance._old_photo = None  # pylint: disable=protected-access
    if not instance.pk:
        return

    try:
        old_instance = Pet.objects.only('photo').get(pk=instance.pk)
    except Pet.DoesNotExist:
        return

    old_name = old_instance.photo.name if old_instance.photo else ''
    new_name = instance.photo.name if instance.photo else ''
    if old_name and old_name != new_name:
        instance._old_photo = old_instance.photo  # pylint: disable=protected-access


@receiver(post_save, sender=Pet)
def cleanup_replaced_pet_photo(sender, instance, **kwargs):
    """Delete old pet photo after a successful update to prevent orphaned files."""
    old_file = getattr(instance, '_old_photo', None)
    if old_file:
        safely_delete_field_file(old_file)


@receiver(post_delete, sender=Pet)
def cleanup_deleted_pet_photo(sender, instance, **kwargs):
    """Delete pet photo when the pet record is removed."""
    safely_delete_field_file(instance.photo)
