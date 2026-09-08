"""Models for attendance and biometric management."""
from datetime import timedelta
import calendar
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.core.files.storage import default_storage
from employees.models import StaffMember
from branches.models import Branch


class DailyAttendance(models.Model):
    """Processed daily attendance for each staff (used by payroll)."""
    
    class AttendanceStatus(models.TextChoices):
        PRESENT = 'PRESENT', 'Present'
        ABSENT = 'ABSENT', 'Absent'
        LATE = 'LATE', 'Late'
        HALF_DAY = 'HALF_DAY', 'Half Day'
        ON_LEAVE = 'ON_LEAVE', 'On Leave'
        APPROVED_ABSENCE = 'APPROVED_ABSENCE', 'Approved Absence'
    
    staff = models.ForeignKey(
        StaffMember,
        on_delete=models.CASCADE,
        related_name='daily_attendance',
    )
    attendance_date = models.DateField(
        help_text='Date of attendance record',
    )
    
    # Expected shift (from schedule)
    expected_start = models.TimeField(
        null=True,
        blank=True,
        help_text='Expected start time from schedule',
    )
    expected_end = models.TimeField(
        null=True,
        blank=True,
        help_text='Expected end time from schedule',
    )
    expected_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text='Expected working hours',
    )
    
    # Actual punch data
    check_in = models.TimeField(
        null=True,
        blank=True,
        help_text='Actual check-in time',
    )
    check_out = models.TimeField(
        null=True,
        blank=True,
        help_text='Actual check-out time',
    )
    
    # Granular 4-Punch Data (Priority 1 Validation)
    morning_in = models.TimeField(
        null=True,
        blank=True,
        help_text='Morning shift check-in time',
    )
    morning_out = models.TimeField(
        null=True,
        blank=True,
        help_text='Morning shift check-out time',
    )
    afternoon_in = models.TimeField(
        null=True,
        blank=True,
        help_text='Afternoon shift check-in time',
    )
    afternoon_out = models.TimeField(
        null=True,
        blank=True,
        help_text='Afternoon shift check-out time',
    )
    
    # Overtime Punch Data
    ot_in = models.TimeField(
        null=True,
        blank=True,
        help_text='Overtime shift check-in time',
    )
    ot_out = models.TimeField(
        null=True,
        blank=True,
        help_text='Overtime shift check-out time',
    )
    ot_hours_calculated = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text='Overtime hours calculated from OT_IN/OT_OUT timestamps',
    )
    
    # Calculated metrics
    total_work_minutes = models.PositiveIntegerField(
        default=0,
        help_text='Total actual worked minutes',
    )
    late_minutes = models.PositiveIntegerField(
        default=0,
        help_text='Minutes late (if check-in is after expected start)',
    )
    overtime_minutes = models.PositiveIntegerField(
        default=0,
        help_text='Minutes worked beyond expected end',
    )
    
    # 4-Punch Validation Status
    four_punch_complete = models.BooleanField(
        default=False,
        help_text='Are all 4 punches (morning in/out, afternoon in/out) present?',
    )
    punch_validation_status = models.CharField(
        max_length=50,
        default='PENDING',
        choices=[
            ('PENDING', 'Pending Validation'),
            ('PASS', 'Passed 4-Punch Validation'),
            ('FAIL', 'Failed 4-Punch Validation'),
            ('FALLBACK', 'Using Fallback (No Granular Punches)'),
        ],
        help_text='Result of 4-punch validation',
    )
    punch_validation_error = models.TextField(
        blank=True,
        help_text='Error details if 4-punch validation failed',
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=AttendanceStatus.choices,
        default=AttendanceStatus.ABSENT,
    )
    is_present = models.BooleanField(
        default=False,
        help_text='Did staff come in this day?',
    )
    
    # Manual adjustment
    is_manually_adjusted = models.BooleanField(
        default=False,
        help_text='Was this record manually edited?',
    )
    adjustment_notes = models.TextField(
        blank=True,
        help_text='Notes about manual adjustments',
    )
    adjusted_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='adjusted_attendance',
    )
    
    # Approval
    is_approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_attendance',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-attendance_date', 'staff']
        unique_together = ['staff', 'attendance_date']
        indexes = [
            models.Index(fields=['staff', 'attendance_date']),
            models.Index(fields=['attendance_date', 'status']),
            models.Index(fields=['is_approved']),
        ]
        verbose_name = 'Daily Attendance'
        verbose_name_plural = 'Daily Attendance'
    
    def __str__(self):
        return f'{self.staff.full_name} — {self.attendance_date} ({self.get_status_display()})'


class MonthlyAttendanceSummary(models.Model):
    """Attendance totals exported by a biometric device for payroll."""

    class ReviewStatus(models.TextChoices):
        IMPORTED = 'IMPORTED', 'Imported'
        APPROVED = 'APPROVED', 'Approved'
        LOCKED = 'LOCKED', 'Locked'

    staff = models.ForeignKey(
        StaffMember,
        on_delete=models.CASCADE,
        related_name='monthly_attendance_summaries',
    )
    period_start = models.DateField()
    period_end = models.DateField()
    
    # Actual Attendance Data (from biometric import)
    working_days = models.PositiveIntegerField(default=0)
    attendance_days = models.PositiveIntegerField(default=0)
    absence_days = models.PositiveIntegerField(default=0)
    late_days = models.PositiveIntegerField(default=0)
    
    # Required Working Days (calculated per period)
    required_working_days = models.PositiveIntegerField(
        default=0,
        help_text='Required working days for this period (cap for attendance)',
    )
    required_working_days_first_half = models.PositiveIntegerField(
        default=0,
        help_text='Required working days for first half (1-15)',
    )
    required_working_days_second_half = models.PositiveIntegerField(
        default=0,
        help_text='Required working days for second half (16-end)',
    )
    
    # 4-Punch Validation Summary
    four_punch_validation_status = models.CharField(
        max_length=50,
        default='PENDING',
        choices=[
            ('PENDING', 'Validation Pending'),
            ('PASS', '100% Pass - All Records Valid'),
            ('PARTIAL', 'Partial Pass - Some Records Invalid'),
            ('FAIL', 'Failed - All Records Invalid'),
            ('NOT_APPLICABLE', 'Not Applicable - Using Fallback Data'),
        ],
        help_text='Overall 4-punch validation status for this month',
    )
    four_punch_violations_count = models.PositiveIntegerField(
        default=0,
        help_text='Number of days with incomplete punch records',
    )
    four_punch_violations = models.JSONField(
        default=list,
        blank=True,
        help_text='List of dates/details with missing punches',
    )
    
    # Overtime Data
    overtime_hours = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    sick_hours = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    leave_hours = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    daily_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    overtime_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    charges = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    real_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    review_status = models.CharField(
        max_length=20,
        choices=ReviewStatus.choices,
        default=ReviewStatus.IMPORTED,
    )
    source_filename = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='monthly_attendance_uploads',
    )
    approved_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_monthly_attendance',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    imported_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-period_start', 'staff']
        constraints = [
            models.UniqueConstraint(
                fields=['staff', 'period_start', 'period_end'],
                name='unique_staff_attendance_month',
            ),
        ]

    def __str__(self):
        return f'{self.staff.full_name} — {self.period_start:%B %Y}'

class AttendanceUpload(models.Model):
    """Original monthly attendance export and its import metadata."""

    period_start = models.DateField()
    period_end = models.DateField()
    source_file = models.FileField(upload_to='attendance/uploads/%Y/%m/')
    source_filename = models.CharField(max_length=255)
    unmatched_biometric_ids = models.JSONField(default=list, blank=True)
    uploaded_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attendance_uploads',
    )
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-period_start', '-imported_at']
        constraints = [
            models.UniqueConstraint(
                fields=['period_start', 'period_end'],
                name='unique_attendance_upload_month',
            ),
        ]

    def __str__(self):
        return f'{self.period_start:%B %Y} — {self.source_filename}'

    def delete(self, *args, **kwargs):
        """Delete the uploaded file and all attendance data for this period."""
        source_name = self.source_file.name if self.source_file else ''
        if self.source_file:
            try:
                self.source_file.delete(save=False)
            except Exception:
                pass

        month_start = self.period_start.replace(day=1)
        month_end = self.period_start.replace(
            day=calendar.monthrange(self.period_start.year, self.period_start.month)[1]
        )
        DailyAttendance.objects.filter(
            attendance_date__range=[month_start, month_end],
        ).delete()
        MonthlyAttendanceSummary.objects.filter(
            period_start__year=self.period_start.year,
            period_start__month=self.period_start.month,
        ).delete()

        source_name = source_name.replace('\\', '/')
        if '/' in source_name:
            directory = source_name.rsplit('/', 1)[0]
            try:
                subdirectories, files = default_storage.listdir(directory)
                for filename in files:
                    default_storage.delete(f'{directory}/{filename}')
                for subdirectory in subdirectories:
                    nested_directory = f'{directory}/{subdirectory}'
                    _, nested_files = default_storage.listdir(nested_directory)
                    for filename in nested_files:
                        default_storage.delete(f'{nested_directory}/{filename}')
            except (FileNotFoundError, OSError):
                pass

        return super().delete(*args, **kwargs)

    @property
    def review_status(self):
        statuses = set(
            MonthlyAttendanceSummary.objects.filter(
                period_start=self.period_start,
                period_end=self.period_end,
            ).values_list('review_status', flat=True)
        )
        if MonthlyAttendanceSummary.ReviewStatus.LOCKED in statuses:
            return MonthlyAttendanceSummary.ReviewStatus.LOCKED
        if statuses and statuses == {MonthlyAttendanceSummary.ReviewStatus.APPROVED}:
            return MonthlyAttendanceSummary.ReviewStatus.APPROVED
        return MonthlyAttendanceSummary.ReviewStatus.IMPORTED
