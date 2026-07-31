# Generated manually
from django.db import migrations


def create_default_statuses(apps, schema_editor):
    """Create default clinical statuses."""
    ClinicalStatus = apps.get_model('settings', 'ClinicalStatus')
    
    default_statuses = [
        {
            'name': 'Healthy',
            'code': 'HEALTHY',
            'description': 'Pet is in good health with no ongoing medical concerns',
            'color': '#4caf50',
            'order': 1,
            'is_active': True,
        },
        {
            'name': 'Under Monitoring',
            'code': 'MONITOR',
            'description': 'Pet is being monitored for a condition or recovery',
            'color': '#ff9800',
            'order': 2,
            'is_active': True,
        },
        {
            'name': 'In Treatment',
            'code': 'TREATMENT',
            'description': 'Pet is currently receiving medical treatment',
            'color': '#2196f3',
            'order': 3,
            'is_active': True,
        },
        {
            'name': 'In Surgery',
            'code': 'SURGERY',
            'description': 'Pet is scheduled for or recovering from surgery',
            'color': '#9c27b0',
            'order': 4,
            'is_active': True,
        },
        {
            'name': 'Pending Diagnostics',
            'code': 'DIAGNOSTICS',
            'description': 'Pet is awaiting diagnostic test results',
            'color': '#607d8b',
            'order': 5,
            'is_active': True,
        },
        {
            'name': 'Critical',
            'code': 'CRITICAL',
            'description': 'Pet requires immediate or intensive medical attention',
            'color': '#f44336',
            'order': 6,
            'is_active': True,
        },
    ]
    
    for status_data in default_statuses:
        ClinicalStatus.objects.get_or_create(
            code=status_data['code'],
            defaults=status_data
        )


def reverse_default_statuses(apps, schema_editor):
    """Remove default clinical statuses."""
    ClinicalStatus = apps.get_model('settings', 'ClinicalStatus')
    codes = ['HEALTHY', 'MONITOR', 'TREATMENT', 'SURGERY', 'DIAGNOSTICS', 'CRITICAL']
    ClinicalStatus.objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0006_clinicalstatus_reasonforvisit'),
    ]

    operations = [
        migrations.RunPython(create_default_statuses, reverse_default_statuses),
    ]
