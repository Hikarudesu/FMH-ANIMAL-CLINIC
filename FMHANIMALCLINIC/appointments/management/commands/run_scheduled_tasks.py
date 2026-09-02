"""Run all recurring clinic jobs from one scheduler entrypoint."""
from io import StringIO

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Run recurring reminders and inventory alert jobs once.'
    lock_key = 'fmh:scheduled-tasks:lock'

    def handle(self, *args, **options):
        if not cache.add(self.lock_key, True, timeout=3300):
            self.stdout.write('A scheduled task run is already in progress.')
            return

        try:
            for command_name in ('send_reminders', 'check_inventory_expiry_alerts'):
                output = StringIO()
                try:
                    call_command(command_name, stdout=output, stderr=output)
                except CommandError as exc:
                    raise CommandError(f'{command_name} failed: {exc}') from exc
                self.stdout.write(output.getvalue().rstrip())
        finally:
            cache.delete(self.lock_key)
