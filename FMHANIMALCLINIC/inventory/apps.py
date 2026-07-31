from django.apps import AppConfig


class InventoryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'inventory'

    def ready(self):
        """Register signal handlers when the app is ready."""
        import inventory.signals  # noqa: F401
