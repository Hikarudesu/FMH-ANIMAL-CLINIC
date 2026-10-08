from django.core.management.base import BaseCommand

from inventory.services import auto_cancel_expired_reservations


class Command(BaseCommand):
    help = 'Cancel pending product reservations past their 24-hour expiry window.'

    def handle(self, *args, **options):
        cancelled = auto_cancel_expired_reservations()
        self.stdout.write(f'Expired reservations cancelled: {cancelled}')
