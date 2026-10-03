"""Expire pet-owner account deactivation requests after their grace period."""

from django.core.management.base import BaseCommand

from accounts.lifecycle import expire_due_owner_accounts


class Command(BaseCommand):
    help = 'Soft-deactivate pet-owner accounts whose one-month grace period has elapsed.'

    def handle(self, *args, **options):
        count = expire_due_owner_accounts()
        self.stdout.write(f'Deactivated {count} pet-owner account(s).')