from django.db import migrations


def discard_imported_real_pay(apps, schema_editor):
    MonthlyAttendanceSummary = apps.get_model('attendance', 'MonthlyAttendanceSummary')
    MonthlyAttendanceSummary.objects.update(real_pay=0)


class Migration(migrations.Migration):
    dependencies = [
        ('attendance', '0011_backfill_legacy_uploads'),
    ]

    operations = [
        migrations.RunPython(discard_imported_real_pay, migrations.RunPython.noop),
    ]