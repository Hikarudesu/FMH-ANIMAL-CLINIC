# Generated migration with data conversion for action_required

import django.db.models.deletion
from django.db import migrations, models


def convert_action_required_to_fk(apps, schema_editor):
    """Convert existing action_required string values to FK IDs."""
    RecordEntry = apps.get_model('records', 'RecordEntry')
    ClinicalStatus = apps.get_model('settings', 'ClinicalStatus')
    
    # Mapping of old string codes to new ClinicalStatus codes
    code_mapping = {
        'HEALTHY': 'HEALTHY',
        'MONITOR': 'MONITOR',
        'TREATMENT': 'TREATMENT',
        'SURGERY': 'SURGERY',
        'DIAGNOSTICS': 'DIAGNOSTICS',
        'CRITICAL': 'CRITICAL',
    }
    
    # Get default status
    default_status = ClinicalStatus.objects.filter(code='HEALTHY').first()
    if not default_status:
        return  # No default status, skip migration
    
    # Update all RecordEntry objects
    for entry in RecordEntry.objects.all():
        if entry.action_required and entry.action_required in code_mapping:
            # Find the corresponding ClinicalStatus
            new_code = code_mapping[entry.action_required]
            try:
                status = ClinicalStatus.objects.get(code=new_code)
                entry.action_required_new_id = status.id
                entry.save(update_fields=['action_required_new_id'])
            except ClinicalStatus.DoesNotExist:
                # Use default if not found
                entry.action_required_new_id = default_status.id
                entry.save(update_fields=['action_required_new_id'])
        else:
            # No action_required or unknown value, use default
            entry.action_required_new_id = default_status.id
            entry.save(update_fields=['action_required_new_id'])


def reverse_conversion(apps, schema_editor):
    """Reverse the conversion."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('records', '0012_medicalrecord_records_med_pet_id_35ac3e_idx_and_more'),
        ('settings', '0016_diagnostictest_medicalrecordtemplate'),
    ]

    operations = [
        # First, add the new fields
        migrations.AddField(
            model_name='medicalrecord',
            name='lab_results',
            field=models.TextField(blank=True, null=True, verbose_name='Lab Results'),
        ),
        migrations.AddField(
            model_name='recordentry',
            name='lab_results',
            field=models.TextField(blank=True, null=True, verbose_name='Lab Results'),
        ),
        migrations.AddField(
            model_name='recordentry',
            name='diagnostic_tests',
            field=models.ManyToManyField(blank=True, help_text='Diagnostic tests associated with this consultation entry.', related_name='record_entries', to='settings.diagnostictest'),
        ),
        # Add new FK field with different name
        migrations.AddField(
            model_name='recordentry',
            name='action_required_new',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='settings.clinicalstatus'),
        ),
        # Run the data migration
        migrations.RunPython(convert_action_required_to_fk, reverse_conversion),
        # Remove the old action_required field
        migrations.RemoveField(
            model_name='recordentry',
            name='action_required',
        ),
        # Rename the new field to action_required
        migrations.RenameField(
            model_name='recordentry',
            old_name='action_required_new',
            new_name='action_required',
        ),
        # Alter the field to add proper attributes
        migrations.AlterField(
            model_name='recordentry',
            name='action_required',
            field=models.ForeignKey(blank=True, help_text='The next step required after this consultation.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='record_entries_action', to='settings.clinicalstatus', verbose_name='Required Action'),
        ),
    ]
