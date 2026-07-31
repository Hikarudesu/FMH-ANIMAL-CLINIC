from django.apps import AppConfig


class BranchesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'branches'

    def ready(self):
        """Register branch signal handlers."""
        import branches.signals  # noqa: F401
