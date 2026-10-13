from django.db import migrations


def add_permanent_position_permission(apps, schema_editor):
    SpecialPermission = apps.get_model('accounts', 'SpecialPermission')
    SpecialPermission.objects.get_or_create(
        code='permanent_position',
        defaults={
            'name': 'Permanent Position',
            'description': (
                'Prevents accounts with this role from changing their assigned '
                'branch in My Profile or Staff management.'
            ),
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0048_user_inactive_reason'),
    ]

    operations = [
        migrations.RunPython(
            add_permanent_position_permission,
            migrations.RunPython.noop,
        ),
    ]