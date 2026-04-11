from django.core.management.base import BaseCommand
from billing.models import Service


class Command(BaseCommand):
    help = 'Add Health Certificate service to the billing system'

    def handle(self, *args, **options):
        health_cert, created = Service.objects.get_or_create(
            name="Health Certificate",
            defaults={
                'price': 650.00,
                'cost': 0.00,
                'category': 'Certificates',
                'active': True,
                'description': 'Health certificate for pets',
                'branch': None,  # Available to all branches
            }
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    'SUCCESS: Health Certificate service created successfully!')
            )
            self.stdout.write(f"   Name: {health_cert.name}")
            self.stdout.write(f"   Price: P{health_cert.price}")
            self.stdout.write(f"   Category: {health_cert.category}")
        else:
            self.stdout.write(
                self.style.WARNING(
                    'INFO: Health Certificate service already exists')
            )
            self.stdout.write(f"   Current price: P{health_cert.price}")
