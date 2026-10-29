from django.db import migrations


OLD_DESCRIPTION = 'Can view the staff dashboard with basic clinic information and statistics'
NEW_DESCRIPTION = (
    'For custom roles only. Shows dashboard content only for modules where the '
    'role has View access, limited to the assigned branch when that module is '
    'branch-restricted. System roles keep their dedicated dashboards.'
)


def update_description(apps, schema_editor):
    SpecialPermission = apps.get_model('accounts', 'SpecialPermission')
    SpecialPermission.objects.filter(
        code='can_access_staff_dashboard',
    ).update(description=NEW_DESCRIPTION)


def restore_description(apps, schema_editor):
    SpecialPermission = apps.get_model('accounts', 'SpecialPermission')
    SpecialPermission.objects.filter(
        code='can_access_staff_dashboard',
    ).update(description=OLD_DESCRIPTION)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0055_disease_geo_mapping_special_permission'),
    ]

    operations = [
        migrations.RunPython(update_description, restore_description),
    ]