from django.db import migrations


def rename_existing_role_codes(apps, schema_editor):
    Role = apps.get_model('accounts', 'Role')
    Role.objects.filter(name='Executive Officer', code='branch_admin').update(
        code='executive_officer'
    )
    Role.objects.filter(name='Assistant Veterinarian', code='vet_assistant').update(
        code='assistant_veterinarian'
    )


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0039_rename_receptionist_role_code'),
    ]

    operations = [
        migrations.RunPython(rename_existing_role_codes, migrations.RunPython.noop),
    ]
