# Generated manually for Vet-in-the-Loop workflow refactoring
# This migration:
# 1. Removes old "Advisor" workflow fields (suggested_procedures, suggested_medications, etc.)
# 2. Adds new "Vet-in-the-Loop" fields (selected_condition, selected_tests, vet_prescription)

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('records', '0012_medicalrecord_records_med_pet_id_35ac3e_idx_and_more'),
        ('diagnostics', '0003_aidiagnosis_fields'),
    ]

    operations = [
        # Update linked_record_entry field
        migrations.AlterField(
            model_name='aidiagnosis',
            name='linked_record_entry',
            field=models.ForeignKey(
                blank=True,
                help_text='RecordEntry created from this diagnosis',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='ai_diagnoses',
                to='records.recordentry'
            ),
        ),

        # Remove old unused fields from "Advisor" workflow
        migrations.RemoveField(
            model_name='aidiagnosis',
            name='suggested_procedures',
        ),
        migrations.RemoveField(
            model_name='aidiagnosis',
            name='suggested_medications',
        ),
        migrations.RemoveField(
            model_name='aidiagnosis',
            name='selected_procedures',
        ),
        migrations.RemoveField(
            model_name='aidiagnosis',
            name='selected_medications',
        ),

        # Add new Vet-in-the-Loop fields
        migrations.AddField(
            model_name='aidiagnosis',
            name='selected_condition',
            field=models.CharField(
                max_length=200,
                blank=True,
                help_text='The condition selected by vet (primary or differential)'
            ),
        ),
        migrations.AddField(
            model_name='aidiagnosis',
            name='selected_tests',
            field=models.JSONField(
                default=list,
                help_text='Tests selected by vet for the treatment plan'
            ),
        ),
        migrations.AddField(
            model_name='aidiagnosis',
            name='vet_prescription',
            field=models.TextField(
                blank=True,
                help_text='Rx entered by vet during review'
            ),
        ),

        # Remove review_notes field (replaced by vet_prescription)
        migrations.RemoveField(
            model_name='aidiagnosis',
            name='review_notes',
        ),
    ]
