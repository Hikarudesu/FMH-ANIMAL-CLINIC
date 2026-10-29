from django.db import migrations


OLD_DESCRIPTION = 'Can view the admin dashboard with advanced statistics and management options'
NEW_DESCRIPTION = (
    'Can view advanced dashboard statistics and management information for '
    'the account\'s assigned branch. Full administrators can view all active '
    'branches.'
)


def update_description(apps, schema_editor):
    SpecialPermission = apps.get_model('accounts', 'SpecialPermission')
    SpecialPermission.objects.filter(
        code='can_access_admin_dashboard',
    ).update(description=NEW_DESCRIPTION)


def restore_description(apps, schema_editor):
    SpecialPermission = apps.get_model('accounts', 'SpecialPermission')
    SpecialPermission.objects.filter(
        code='can_access_admin_dashboard',
    ).update(description=OLD_DESCRIPTION)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0056_update_staff_dashboard_permission_description'),
    ]

    operations = [
        migrations.RunPython(update_description, restore_description),
    ]