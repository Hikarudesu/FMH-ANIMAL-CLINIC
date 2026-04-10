"""Signal handlers for settings."""

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import SystemSetting, ClinicProfile
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
