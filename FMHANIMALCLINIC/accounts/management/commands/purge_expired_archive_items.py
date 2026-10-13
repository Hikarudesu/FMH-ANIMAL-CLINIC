"""Permanently remove archived items after the configured retention period."""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from billing.models import Service
from inventory.models import Product
from patients.models import Pet
from records.models import MedicalFile, MedicalRecord, RecordEntry


class Command(BaseCommand):
    help = 'Permanently delete archived records older than 30 days.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report expired archive counts without deleting anything.',
        )

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=30)
        models = (
            ('medical files', MedicalFile),
            ('visit histories', RecordEntry),
            ('medical records', MedicalRecord),
            ('pets / patients', Pet),
            ('inventory items', Product),
            ('clinic services', Service),
        )
        expired = {
            label: model.all_objects.filter(
                is_deleted=True,
                deleted_at__lte=cutoff,
            )
            for label, model in models
        }
        counts = {label: queryset.count() for label, queryset in expired.items()}

        if options['dry_run']:
            self.stdout.write('Dry run; no archived items were removed.')
        else:
            with transaction.atomic():
                for medical_file in expired['medical files'].iterator():
                    if medical_file.file:
                        medical_file.file.delete(save=False)
                for queryset in expired.values():
                    queryset.delete()

        action = 'Would permanently delete' if options['dry_run'] else 'Permanently deleted'
        for label, count in counts.items():
            self.stdout.write(f'{action} {count} expired {label}.')
