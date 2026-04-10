"""App configuration for settings."""

from django.apps import AppConfig


class SettingsConfig(AppConfig):
    """Configuration for the settings app."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'settings'
    verbose_name = 'System Settings'

    def ready(self):
        """Register signal handlers when the app is ready."""
        import settings.signals  # noqa: F401
