from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = 'accounts'
    
    def ready(self):
        """Import signal handlers when the app is ready."""
        import accounts.signals  # noqa: F401
        import accounts.activity_signals  # noqa: F401
