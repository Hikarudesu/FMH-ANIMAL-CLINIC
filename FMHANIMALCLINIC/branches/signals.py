"""Signal handlers for branch media lifecycle."""

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from utils.file_cleanup import safely_delete_field_file
from .models import Branch


@receiver(pre_save, sender=Branch)
def stash_old_branch_logo(sender, instance, **kwargs):
    """Track previous branch logo so replacement cleanup can run after save."""
    instance._old_logo = None  # pylint: disable=protected-access
    if not instance.pk:
        return

    try:
        old_instance = Branch.objects.only('logo').get(pk=instance.pk)
    except Branch.DoesNotExist:
        return

    old_name = old_instance.logo.name if old_instance.logo else ''
    new_name = instance.logo.name if instance.logo else ''
    if old_name and old_name != new_name:
        instance._old_logo = old_instance.logo  # pylint: disable=protected-access


@receiver(post_save, sender=Branch)
def cleanup_replaced_branch_logo(sender, instance, **kwargs):
    """Delete previous branch logo after the new file has been saved."""
    old_file = getattr(instance, '_old_logo', None)
    if old_file:
        safely_delete_field_file(old_file)


@receiver(post_delete, sender=Branch)
def cleanup_deleted_branch_logo(sender, instance, **kwargs):
    """Delete branch logo from storage when branch record is removed."""
    safely_delete_field_file(instance.logo)
