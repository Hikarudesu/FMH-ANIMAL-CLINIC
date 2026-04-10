"""Utility functions for accessing system settings."""

from django.core.cache import cache

CACHE_TIMEOUT = 300  # 5 minutes
CACHE_KEY_PREFIX = 'fmh_setting_'


def get_setting(key, default=None, use_cache=True):
    """
    Retrieve a system setting value with type coercion.

    Args:
        key: The setting key to retrieve
        default: Default value if setting doesn't exist
        use_cache: Whether to use cached values (default True)

    Returns:
        The setting value converted to its proper Python type

    Usage:
        slot_duration = get_setting('appointment_slot_duration', default=30)
        maintenance_mode = get_setting('system_maintenance_mode', default=False)
    """
    cache_key = f"{CACHE_KEY_PREFIX}{key}"

    if use_cache:
        cached_value = cache.get(cache_key)
        if cached_value is not None:
            return cached_value

    from settings.models import SystemSetting

    try:
        setting = SystemSetting.objects.get(key=key)
        value = setting.get_typed_value()

        if use_cache:
            cache.set(cache_key, value, CACHE_TIMEOUT)

        return value
    except SystemSetting.DoesNotExist:
        return default


def set_setting(key, value, user=None, category=None, description=None):
    """
    Update a system setting and invalidate cache.

    Args:
        key: The setting key to update
        value: The new value
        user: Optional user for activity logging
        category: Optional category for new settings
        description: Optional description for new settings

    Returns:
        The updated SystemSetting instance

    Usage:
        set_setting('appointment_slot_duration', 45, user=request.user)
    """
    from settings.models import SystemSetting
    from accounts.models import ActivityLog

    setting, created = SystemSetting.objects.get_or_create(
        key=key,
        defaults={
            'category': category or SystemSetting.Category.SYSTEM,
            'description': description or '',
        }
    )
    old_value = setting.value

    # Set the typed value (handles type conversion)
    setting.set_typed_value(value)
    setting.save()

    # Invalidate cache
    cache_key = f"{CACHE_KEY_PREFIX}{key}"
    cache.delete(cache_key)

    # Log change if user provided
    if user:
        if created:
            action = f"Created setting: {key}"
            details = f"Initial value: {setting.value}"
        else:
            action = f"Updated setting: {key}"
            details = f"Changed from '{old_value}' to '{setting.value}'"

        ActivityLog.objects.create(
            user=user,
            action=action,
            category=ActivityLog.Category.SYSTEM,
            branch=user.branch if hasattr(user, 'branch') else None,
            details=details
        )

    return setting


def get_settings_by_category(category):
    """
    Retrieve all settings for a category as a dictionary.

    Args:
        category: The category string (e.g., 'APPOINTMENT')

    Returns:
        Dictionary mapping setting keys to their typed values

    Usage:
        appt_settings = get_settings_by_category('APPOINTMENT')
    """
    from settings.models import SystemSetting

    settings = SystemSetting.objects.filter(category=category)
    return {s.key: s.get_typed_value() for s in settings}


def get_clinic_profile():
    """
    Retrieve the singleton clinic profile.

    Returns:
        ClinicProfile instance

    Usage:
        clinic = get_clinic_profile()
        print(clinic.name)
    """
    cache_key = f"{CACHE_KEY_PREFIX}clinic_profile"
    cached = cache.get(cache_key)

    if cached:
        return cached

    from settings.models import ClinicProfile

    profile = ClinicProfile.get_instance()
    cache.set(cache_key, profile, CACHE_TIMEOUT)
    return profile


def invalidate_setting_cache(key=None):
    """
    Invalidate setting cache(s).

    Args:
        key: Specific key to invalidate, or None for all settings

    Usage:
        invalidate_setting_cache('appointment_slot_duration')  # Single key
        invalidate_setting_cache()  # All settings
    """
    if key:
        cache.delete(f"{CACHE_KEY_PREFIX}{key}")
    else:
        # Clear all setting caches
        from settings.models import SystemSetting
        for setting in SystemSetting.objects.all():
            cache.delete(f"{CACHE_KEY_PREFIX}{setting.key}")
        cache.delete(f"{CACHE_KEY_PREFIX}clinic_profile")


def invalidate_clinic_profile_cache():
    """Invalidate the clinic profile cache."""
    cache.delete(f"{CACHE_KEY_PREFIX}clinic_profile")
