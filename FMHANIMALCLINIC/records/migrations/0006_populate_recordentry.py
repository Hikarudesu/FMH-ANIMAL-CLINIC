"""
Data migration: seed a RecordEntry for every existing MedicalRecord so
that existing visit data is preserved under the new entry-based scheme.
"""
from django.db import migrations


def forward_populate_entries(apps, schema_editor):
    MedicalRecord = apps.get_model('records', 'MedicalRecord')
    RecordEntry = apps.get_model('records', 'RecordEntry')

    for record in MedicalRecord.objects.all():
        # Only create an entry if this record has any visit data
        if not RecordEntry.objects.filter(record=record).exists():
            RecordEntry.objects.create(
                record=record,
                vet=record.vet,
                date_recorded=record.date_recorded,
                weight=record.weight,
                temperature=record.temperature,
                history_clinical_signs=record.history_clinical_signs,
                treatment=record.treatment,
                rx=record.rx,
                ff_up=record.ff_up,
            )


def reverse_populate_entries(apps, schema_editor):
    RecordEntry = apps.get_model('records', 'RecordEntry')
    RecordEntry.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('records', '0005_recordentry_add'),
    ]

    operations = [
        migrations.RunPython(forward_populate_entries, reverse_populate_entries),
    ]
