"""Initial migration for attendance app."""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('employees', '0008_staffmember_default_custom_deductions'),
        ('branches', '0006_branch_is_main_source'),
        ('accounts', '0035_add_attendance_module'),
    ]

    operations = [
        migrations.CreateModel(
            name='BiometricDevice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('device_name', models.CharField(help_text='e.g., Branch A Main Entrance', max_length=100)),
                ('device_model', models.CharField(default='Fingerprint Scanner', help_text='e.g., ZKTeco K20, Suprema BioEntry', max_length=100)),
                ('device_serial', models.CharField(help_text='Serial number or unique ID from device', max_length=100, unique=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, help_text='IP address if connected to network', null=True)),
                ('port', models.PositiveIntegerField(default=5005, help_text='Device connection port')),
                ('connection_type', models.CharField(choices=[('USB', 'USB Export'), ('LAN', 'Local Network'), ('API', 'Device API'), ('MANUAL', 'Manual CSV/Excel Import')], default='USB', help_text='How device syncs with system', max_length=50)),
                ('status', models.CharField(choices=[('ACTIVE', 'Active'), ('INACTIVE', 'Inactive'), ('MAINTENANCE', 'Maintenance'), ('ERROR', 'Error')], default='ACTIVE', max_length=20)),
                ('is_active', models.BooleanField(default=True)),
                ('last_sync_at', models.DateTimeField(blank=True, help_text='Last successful sync time', null=True)),
                ('sync_interval_minutes', models.PositiveIntegerField(default=15, help_text='Auto-sync interval (unused if MANUAL)')),
                ('notes', models.TextField(blank=True, help_text='Location, setup notes, etc.')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='biometric_devices', to='branches.branch')),
            ],
            options={
                'verbose_name': 'Biometric Device',
                'verbose_name_plural': 'Biometric Devices',
                'ordering': ['branch', 'device_name'],
            },
        ),
        migrations.CreateModel(
            name='StaffBiometricMapping',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('external_user_id', models.CharField(help_text='Device user ID (e.g., 12, 17, etc.)', max_length=50)),
                ('device_username', models.CharField(blank=True, help_text='Optional username on device', max_length=100)),
                ('enrollment_status', models.CharField(choices=[('PENDING', 'Pending Enrollment'), ('ENROLLED', 'Enrolled'), ('INACTIVE', 'Inactive')], default='PENDING', max_length=20)),
                ('is_active', models.BooleanField(default=True, help_text='Is this mapping currently used?')),
                ('enrolled_at', models.DateTimeField(blank=True, null=True)),
                ('last_punch_at', models.DateTimeField(blank=True, help_text='Last time this mapping recorded a punch', null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='staff_mappings', to='attendance.biometricdevice')),
                ('staff', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='biometric_mappings', to='employees.staffmember')),
            ],
            options={
                'verbose_name': 'Staff Biometric Mapping',
                'verbose_name_plural': 'Staff Biometric Mappings',
                'ordering': ['staff', 'device'],
            },
        ),
        migrations.CreateModel(
            name='AttendanceLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('external_user_id', models.CharField(help_text='Device user ID from raw punch', max_length=50)),
                ('punch_datetime', models.DateTimeField(help_text='When the punch was recorded')),
                ('punch_type', models.CharField(choices=[('CHECK_IN', 'Check In'), ('CHECK_OUT', 'Check Out'), ('BREAK_IN', 'Break In'), ('BREAK_OUT', 'Break Out'), ('UNKNOWN', 'Unknown')], default='CHECK_IN', max_length=20)),
                ('raw_payload', models.JSONField(blank=True, default=dict, help_text='Original data from device (full record)')),
                ('source_record_id', models.CharField(help_text='Unique ID from device to prevent duplicates', max_length=100, unique=True)),
                ('sync_status', models.CharField(choices=[('PENDING', 'Pending'), ('MATCHED', 'Matched to Staff'), ('UNMATCHED', 'Unmatched'), ('DUPLICATE', 'Duplicate'), ('ERROR', 'Error')], default='PENDING', max_length=20)),
                ('sync_notes', models.TextField(blank=True)),
                ('imported_at', models.DateTimeField(auto_now_add=True)),
                ('processed_at', models.DateTimeField(blank=True, null=True)),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attendance_logs', to='attendance.biometricdevice')),
                ('mapping', models.ForeignKey(blank=True, help_text='Matched staff mapping', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='attendance_logs', to='attendance.staffbiometricmapping')),
            ],
            options={
                'verbose_name': 'Attendance Log',
                'verbose_name_plural': 'Attendance Logs',
                'ordering': ['-punch_datetime'],
            },
        ),
        migrations.CreateModel(
            name='DailyAttendance',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('attendance_date', models.DateField(help_text='Date of attendance record')),
                ('expected_start', models.TimeField(blank=True, help_text='Expected start time from schedule', null=True)),
                ('expected_end', models.TimeField(blank=True, help_text='Expected end time from schedule', null=True)),
                ('expected_hours', models.DecimalField(decimal_places=2, default=0, help_text='Expected working hours', max_digits=5)),
                ('check_in', models.TimeField(blank=True, help_text='Actual check-in time', null=True)),
                ('check_out', models.TimeField(blank=True, help_text='Actual check-out time', null=True)),
                ('total_work_minutes', models.PositiveIntegerField(default=0, help_text='Total actual worked minutes')),
                ('late_minutes', models.PositiveIntegerField(default=0, help_text='Minutes late (if check-in is after expected start)')),
                ('overtime_minutes', models.PositiveIntegerField(default=0, help_text='Minutes worked beyond expected end')),
                ('status', models.CharField(choices=[('PRESENT', 'Present'), ('ABSENT', 'Absent'), ('LATE', 'Late'), ('HALF_DAY', 'Half Day'), ('ON_LEAVE', 'On Leave'), ('APPROVED_ABSENCE', 'Approved Absence')], default='ABSENT', max_length=20)),
                ('is_present', models.BooleanField(default=False, help_text='Did staff come in this day?')),
                ('is_manually_adjusted', models.BooleanField(default=False, help_text='Was this record manually edited?')),
                ('adjustment_notes', models.TextField(blank=True, help_text='Notes about manual adjustments')),
                ('is_approved', models.BooleanField(default=False)),
                ('approved_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('adjusted_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='adjusted_attendance', to='accounts.user')),
                ('approved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='approved_attendance', to='accounts.user')),
                ('staff', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='daily_attendance', to='employees.staffmember')),
            ],
            options={
                'verbose_name': 'Daily Attendance',
                'verbose_name_plural': 'Daily Attendance',
                'ordering': ['-attendance_date', 'staff'],
            },
        ),
        migrations.CreateModel(
            name='AttendanceException',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('attendance_date', models.DateField()),
                ('exception_type', models.CharField(choices=[('ABSENT', 'Absent'), ('HALF_DAY_ABSENCE', 'Half Day Absence'), ('LATE', 'Late'), ('EARLY_CHECKOUT', 'Early Checkout'), ('SICK_LEAVE', 'Sick Leave'), ('VACATION_LEAVE', 'Vacation Leave'), ('SPECIAL_LEAVE', 'Special Leave'), ('NO_PUNCH', 'No Punch Data'), ('DUPLICATE_PUNCH', 'Duplicate Punch'), ('INVALID_TIME', 'Invalid Time'), ('MANUAL_OVERRIDE', 'Manual Override')], max_length=30)),
                ('description', models.TextField(blank=True, help_text='Reason or notes (e.g., "Traffic", "Medical emergency")')),
                ('resolution_status', models.CharField(choices=[('PENDING', 'Pending'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected'), ('OVERRIDDEN', 'Overridden')], default='PENDING', max_length=20)),
                ('resolution_notes', models.TextField(blank=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('resolved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='resolved_exceptions', to='accounts.user')),
                ('staff', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attendance_exceptions', to='employees.staffmember')),
            ],
            options={
                'verbose_name': 'Attendance Exception',
                'verbose_name_plural': 'Attendance Exceptions',
                'ordering': ['-attendance_date', 'staff'],
            },
        ),
        migrations.AddConstraint(
            model_name='staffbiometricmapping',
            constraint=models.UniqueConstraint(fields=['device', 'external_user_id'], name='unique_device_user_id'),
        ),
        migrations.AddConstraint(
            model_name='dailyattendance',
            constraint=models.UniqueConstraint(fields=['staff', 'attendance_date'], name='unique_staff_date_attendance'),
        ),
        migrations.AddIndex(
            model_name='staffbiometricmapping',
            index=models.Index(fields=['staff', 'is_active'], name='attendance_s_staff_i_99a1b2_idx'),
        ),
        migrations.AddIndex(
            model_name='staffbiometricmapping',
            index=models.Index(fields=['device', 'enrollment_status'], name='attendance_s_device__99a1b2_idx'),
        ),
        migrations.AddIndex(
            model_name='attendancelog',
            index=models.Index(fields=['external_user_id', 'punch_datetime'], name='attendance_a_externa_99a1b2_idx'),
        ),
        migrations.AddIndex(
            model_name='attendancelog',
            index=models.Index(fields=['device', 'punch_datetime'], name='attendance_a_device__99a1b2_idx'),
        ),
        migrations.AddIndex(
            model_name='attendancelog',
            index=models.Index(fields=['sync_status'], name='attendance_a_sync_st_99a1b2_idx'),
        ),
        migrations.AddIndex(
            model_name='dailyattendance',
            index=models.Index(fields=['staff', 'attendance_date'], name='attendance_d_staff_a_99a1b2_idx'),
        ),
        migrations.AddIndex(
            model_name='dailyattendance',
            index=models.Index(fields=['attendance_date', 'status'], name='attendance_d_attenda_99a1b2_idx'),
        ),
        migrations.AddIndex(
            model_name='dailyattendance',
            index=models.Index(fields=['is_approved'], name='attendance_d_is_appr_99a1b2_idx'),
        ),
        migrations.AddIndex(
            model_name='attendanceexception',
            index=models.Index(fields=['staff', 'attendance_date'], name='attendance_a_staff_a_99a1b2_idx'),
        ),
        migrations.AddIndex(
            model_name='attendanceexception',
            index=models.Index(fields=['exception_type', 'resolution_status'], name='attendance_a_exceptio_99a1b2_idx'),
        ),
    ]
