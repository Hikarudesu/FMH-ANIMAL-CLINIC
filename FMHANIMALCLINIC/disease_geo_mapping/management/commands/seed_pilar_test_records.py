from django.core.management.base import BaseCommand
from django.db import transaction
from datetime import date, timedelta


class Command(BaseCommand):
    help = 'Seed 10 test medical records for Pilar branch for Disease Geo Mapping demos'

    def handle(self, *args, **options):
        from branches.models import Branch
        from patients.models import Pet
        from records.models import MedicalRecord, RecordEntry

        branch = Branch.objects.filter(name__icontains='pilar').first()
        if not branch:
            self.stderr.write('Pilar branch not found. Aborting.')
            return

        base_date = date.today() - timedelta(days=7)
        symptoms = (
            'Persistent cough, labored breathing, nasal discharge, occasional fever',
        )
        treatment = 'Supportive care, nebulization, antibiotics as indicated'
        rx = 'Amoxicillin 250mg PO BID for 7 days; cough suppressant PRN'

        created = 0
        with transaction.atomic():
            for i in range(1, 11):
                pet_name = f'test-{i}'
                pet, _ = Pet.objects.get_or_create(
                    name=pet_name,
                    defaults={
                        'species': 'Dog',
                        'sex': 'MALE',
                        'branch': branch,
                        'guest_owner_name': 'Test Owner',
                        'guest_owner_phone': '000-000-0000',
                    }
                )

                mr = MedicalRecord.objects.create(
                    pet=pet,
                    branch=branch,
                    date_recorded=base_date,
                    history_clinical_signs=symptoms[0],
                    treatment=treatment,
                    rx=rx,
                )

                RecordEntry.objects.create(
                    record=mr,
                    date_recorded=base_date,
                    history_clinical_signs=symptoms[0],
                    treatment=treatment,
                    rx=rx,
                )

                created += 1

        self.stdout.write(self.style.SUCCESS(f'Created {created} test medical records in branch: {branch.name}'))
