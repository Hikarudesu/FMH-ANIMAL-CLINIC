# Generated manually
from django.db import migrations


def create_default_reasons(apps, schema_editor):
    """Create default reasons for visit."""
    ReasonForVisit = apps.get_model('settings', 'ReasonForVisit')
    
    default_reasons = [
        {
            'name': 'General Consultation',
            'code': 'GENERAL',
            'description': 'General health checkup or consultation',
            'order': 1,
            'is_active': True,
        },
        {
            'name': 'Routine Check-up',
            'code': 'CHECKUP',
            'description': 'Regular wellness examination',
            'order': 2,
            'is_active': True,
        },
        {
            'name': 'Vaccination',
            'code': 'VACCINATION',
            'description': 'Scheduled vaccination appointment',
            'order': 3,
            'is_active': True,
        },
        {
            'name': 'Surgery',
            'code': 'SURGERY',
            'description': 'Scheduled surgical procedure',
            'order': 4,
            'is_active': True,
        },
        {
            'name': 'Emergency',
            'code': 'EMERGENCY',
            'description': 'Urgent medical attention required',
            'order': 5,
            'is_active': True,
        },
        {
            'name': 'Follow-up',
            'code': 'FOLLOWUP',
            'description': 'Follow-up visit after treatment',
            'order': 6,
            'is_active': True,
        },
    ]
    
    for reason_data in default_reasons:
        ReasonForVisit.objects.get_or_create(
            code=reason_data['code'],
            defaults=reason_data
        )


def reverse_default_reasons(apps, schema_editor):
    """Remove default reasons for visit."""
    ReasonForVisit = apps.get_model('settings', 'ReasonForVisit')
    codes = ['GENERAL', 'CHECKUP', 'VACCINATION', 'SURGERY', 'EMERGENCY', 'FOLLOWUP']
    ReasonForVisit.objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0007_seed_default_clinical_statuses'),
    ]

    operations = [
        migrations.RunPython(create_default_reasons, reverse_default_reasons),
    ]
