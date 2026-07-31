# Generated manually
from django.db import migrations, models


def create_default_shift_types(apps, schema_editor):
    """Create default shift types used by staff schedules."""
    ShiftTypeOption = apps.get_model('settings', 'ShiftTypeOption')

    default_shift_types = [
        {
            'name': 'General',
            'code': 'GENERAL',
            'description': 'Regular clinic schedule',
            'order': 1,
            'is_active': True,
        },
        {
            'name': 'Surgery Only',
            'code': 'SURGERY',
            'description': 'Surgical procedures only',
            'order': 2,
            'is_active': True,
        },
        {
            'name': 'Telehealth',
            'code': 'TELEHEALTH',
            'description': 'Virtual or remote consults',
            'order': 3,
            'is_active': True,
        },
        {
            'name': 'Break',
            'code': 'BREAK',
            'description': 'Break or unavailable period',
            'order': 4,
            'is_active': True,
        },
        {
            'name': 'Check-up Only',
            'code': 'CHECKUP',
            'description': 'Routine check-up appointments only',
            'order': 5,
            'is_active': True,
        },
    ]

    for shift_type_data in default_shift_types:
        ShiftTypeOption.objects.get_or_create(
            code=shift_type_data['code'],
            defaults=shift_type_data,
        )


def reverse_default_shift_types(apps, schema_editor):
    """Remove default shift types."""
    ShiftTypeOption = apps.get_model('settings', 'ShiftTypeOption')
    codes = ['GENERAL', 'SURGERY', 'TELEHEALTH', 'BREAK', 'CHECKUP']
    ShiftTypeOption.objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0008_seed_default_reasons_for_visit'),
    ]

    operations = [
        migrations.CreateModel(
            name='ShiftTypeOption',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='Display name for this shift type (e.g., "General")', max_length=100)),
                ('code', models.CharField(help_text='Unique code for internal use (e.g., "GENERAL")', max_length=30, unique=True)),
                ('description', models.TextField(blank=True, help_text='Optional description for staff reference')),
                ('order', models.PositiveIntegerField(default=0, help_text='Display order (lower numbers appear first)')),
                ('is_active', models.BooleanField(default=True, help_text='Inactive shift types will not appear in schedule forms')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Shift Type',
                'verbose_name_plural': 'Shift Types',
                'ordering': ['order', 'name'],
            },
        ),
        migrations.RunPython(create_default_shift_types, reverse_default_shift_types),
    ]