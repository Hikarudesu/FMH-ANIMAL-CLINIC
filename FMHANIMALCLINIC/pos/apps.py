from django.apps import AppConfig


class PosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'pos'
    verbose_name = 'Point of Sale'

    def ready(self):
        from . import signals  # noqa: F401
