from django.apps import AppConfig


class RecordsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'records'

    def ready(self):
        # Import models to register signal handlers defined there
        import records.models  # noqa: F401
