"""Signal handlers for settings."""

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from utils.file_cleanup import safely_delete_field_file

from .models import (
    SystemSetting,
    ClinicProfile,
    SectionContent,
    Service,
    Veterinarian,
)
from .utils import invalidate_setting_cache, invalidate_clinic_profile_cache

# Store old values before save for logging
_setting_old_values = {}


@receiver(pre_save, sender=SystemSetting)
def capture_old_setting_value(sender, instance, **kwargs):
    """Capture the old value before saving for logging."""
    if instance.pk:
        try:
            old_instance = SystemSetting.objects.get(pk=instance.pk)
            _setting_old_values[instance.pk] = old_instance.value
        except SystemSetting.DoesNotExist:
            _setting_old_values[instance.pk] = None


@receiver(post_save, sender=SystemSetting)
def invalidate_setting_cache_on_save(sender, instance, created, **kwargs):
    """Invalidate cache when a setting is saved."""
    invalidate_setting_cache(instance.key)
    # Clean up old value tracking
    _setting_old_values.pop(instance.pk, None)


@receiver(post_save, sender=ClinicProfile)
def invalidate_clinic_profile_cache_on_save(sender, instance, created, **kwargs):
    """Invalidate clinic profile cache when saved."""
    invalidate_clinic_profile_cache()


def _stash_old_file(instance, model_cls, field_name, attr_name):
    """Capture old file value before save so it can be removed after successful update."""
    setattr(instance, attr_name, None)
    if not instance.pk:
        return

    try:
        old_instance = model_cls.objects.only(field_name).get(pk=instance.pk)
    except model_cls.DoesNotExist:
        return

    old_file = getattr(old_instance, field_name)
    new_file = getattr(instance, field_name)
    old_name = old_file.name if old_file else ''
    new_name = new_file.name if new_file else ''
    if old_name and old_name != new_name:
        setattr(instance, attr_name, old_file)


def _cleanup_stashed_file(instance, attr_name):
    """Delete a previously stashed file after successful save."""
    old_file = getattr(instance, attr_name, None)
    if old_file:
        safely_delete_field_file(old_file)


@receiver(pre_save, sender=ClinicProfile)
def stash_old_clinic_logo(sender, instance, **kwargs):
    """Capture old clinic logo before update."""
    _stash_old_file(instance, ClinicProfile, 'logo', '_old_logo')


@receiver(post_save, sender=ClinicProfile)
def cleanup_old_clinic_logo(sender, instance, **kwargs):
    """Delete replaced clinic logo after successful save."""
    _cleanup_stashed_file(instance, '_old_logo')


@receiver(post_delete, sender=ClinicProfile)
def cleanup_deleted_clinic_logo(sender, instance, **kwargs):
    """Delete clinic logo from storage when deleting record."""
    safely_delete_field_file(instance.logo)


@receiver(pre_save, sender=SectionContent)
def stash_old_section_image(sender, instance, **kwargs):
    """Capture old section image before update."""
    _stash_old_file(instance, SectionContent, 'image', '_old_image')


@receiver(post_save, sender=SectionContent)
def cleanup_old_section_image(sender, instance, **kwargs):
    """Delete replaced section image after successful save."""
    _cleanup_stashed_file(instance, '_old_image')


@receiver(post_delete, sender=SectionContent)
def cleanup_deleted_section_image(sender, instance, **kwargs):
    """Delete section image from storage when deleting record."""
    safely_delete_field_file(instance.image)


@receiver(pre_save, sender=Service)
def stash_old_service_image(sender, instance, **kwargs):
    """Capture old service image before update."""
    _stash_old_file(instance, Service, 'image', '_old_image')


@receiver(post_save, sender=Service)
def cleanup_old_service_image(sender, instance, **kwargs):
    """Delete replaced service image after successful save."""
    _cleanup_stashed_file(instance, '_old_image')


@receiver(post_delete, sender=Service)
def cleanup_deleted_service_image(sender, instance, **kwargs):
    """Delete service image from storage when deleting record."""
    safely_delete_field_file(instance.image)


@receiver(pre_save, sender=Veterinarian)
def stash_old_veterinarian_photo(sender, instance, **kwargs):
    """Capture old veterinarian photo before update."""
    _stash_old_file(instance, Veterinarian, 'photo', '_old_photo')


@receiver(post_save, sender=Veterinarian)
def cleanup_old_veterinarian_photo(sender, instance, **kwargs):
    """Delete replaced veterinarian photo after successful save."""
    _cleanup_stashed_file(instance, '_old_photo')


@receiver(post_delete, sender=Veterinarian)
def cleanup_deleted_veterinarian_photo(sender, instance, **kwargs):
    """Delete veterinarian photo from storage when deleting record."""
    safely_delete_field_file(instance.photo)
