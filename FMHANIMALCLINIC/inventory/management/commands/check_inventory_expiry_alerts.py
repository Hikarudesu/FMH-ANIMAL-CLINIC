"""Management command to generate inventory expiry alerts."""

from django.core.management.base import BaseCommand

from inventory.expiry_alerts import run_inventory_expiry_alert_job


class Command(BaseCommand):
    help = 'Create inventory expiry warning notifications using inventory_expiry_warning_days.'

    def handle(self, *args, **options):
        summary = run_inventory_expiry_alert_job()

        if not summary.get('alerts_enabled'):
            self.stdout.write(
                self.style.WARNING('Inventory alerts are disabled (inventory_enable_alerts=false).')
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                'Inventory expiry alert job complete. '
                f"warning_days={summary.get('warning_days')} | "
                f"products_scanned={summary.get('products_scanned')} | "
                f"notifications_created={summary.get('notifications_created')}"
            )
        )
