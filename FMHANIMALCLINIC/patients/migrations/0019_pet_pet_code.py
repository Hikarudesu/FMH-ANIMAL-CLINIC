import secrets
import string

from django.db import migrations, models


def populate_pet_codes(apps, schema_editor):
    Pet = apps.get_model('patients', 'Pet')
    database = schema_editor.connection.alias
    alphabet = string.ascii_uppercase + string.digits
    existing_codes = set(
        Pet.objects.using(database).exclude(pet_code__isnull=True)
        .exclude(pet_code='')
        .values_list('pet_code', flat=True)
    )

    for pet in Pet.objects.using(database).filter(pet_code__isnull=True).iterator():
        code = ''.join(secrets.choice(alphabet) for _ in range(10))
        while code in existing_codes:
            code = ''.join(secrets.choice(alphabet) for _ in range(10))
        pet.pet_code = code
        pet.save(update_fields=['pet_code'])
        existing_codes.add(code)


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0018_pet_branch'),
    ]

    operations = [
        migrations.AddField(
            model_name='pet',
            name='pet_code',
            field=models.CharField(max_length=10, null=True),
        ),
        migrations.RunPython(populate_pet_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='pet',
            name='pet_code',
            field=models.CharField(editable=False, max_length=10, unique=True),
        ),
    ]
