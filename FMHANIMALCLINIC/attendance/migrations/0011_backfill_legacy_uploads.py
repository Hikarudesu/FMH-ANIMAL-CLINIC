from django.db import migrations


def backfill_legacy_uploads(apps, schema_editor):
    MonthlyAttendanceSummary = apps.get_model('attendance', 'MonthlyAttendanceSummary')
    AttendanceUpload = apps.get_model('attendance', 'AttendanceUpload')
    periods = MonthlyAttendanceSummary.objects.values(
        'period_start', 'period_end', 'source_filename', 'uploaded_by_id'
    ).distinct()
    for period in periods:
        AttendanceUpload.objects.get_or_create(
            period_start=period['period_start'],
            period_end=period['period_end'],
            defaults={
                'source_filename': period['source_filename'] or 'Legacy import (original file unavailable)',
                'uploaded_by_id': period['uploaded_by_id'],
                'source_file': '',
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ('attendance', '0010_attendanceupload'),
    ]

    operations = [
        migrations.RunPython(backfill_legacy_uploads, migrations.RunPython.noop),
    ]
