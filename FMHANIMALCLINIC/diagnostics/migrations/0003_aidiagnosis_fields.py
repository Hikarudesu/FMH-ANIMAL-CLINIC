# Generated manually for AI diagnostic advisor workflow

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('records', '0001_initial'),
        ('diagnostics', '0002_remove_confidence_field'),
    ]

    operations = [
        migrations.AddField(
            model_name='aidiagnosis',
            name='suggested_procedures',
            field=models.JSONField(
                default=list,
                help_text='List of AI-suggested procedures/treatments'
            ),
        ),
        migrations.AddField(
            model_name='aidiagnosis',
            name='suggested_medications',
            field=models.JSONField(
                default=list,
                help_text='List of AI-suggested medications'
            ),
        ),
        migrations.AddField(
            model_name='aidiagnosis',
            name='selected_procedures',
            field=models.JSONField(
                default=list,
                help_text='Procedures selected by veterinarian for transfer'
            ),
        ),
        migrations.AddField(
            model_name='aidiagnosis',
            name='selected_medications',
            field=models.JSONField(
                default=list,
                help_text='Medications selected by veterinarian for transfer'
            ),
        ),
        migrations.AddField(
            model_name='aidiagnosis',
            name='linked_record_entry',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='ai_diagnoses',
                to='records.recordentry'
            ),
        ),
    ]
