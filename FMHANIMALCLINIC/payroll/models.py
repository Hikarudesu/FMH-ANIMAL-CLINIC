"""
Simplified Payroll Models for FMH Animal Clinic.

WORKFLOW (NEW):
1. Load Period - Select payroll period and semi-monthly option
2. Edit Payslips - Adjust deductions, bonuses, overtime BEFORE calculation
3. Generate Payroll - Lock in calculations with transaction.atomic()
4. Release Payroll - Mark as released and send payslips

SEMI-MONTHLY SUPPORT:
- Option A: 1st to 15th of the month
- Option B: 16th to End of the month (28th/29th/30th/31st)
"""
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, timedelta
import calendar
import logging

from django.db import models
from django.db.models import Q, Sum
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from employees.models import StaffMember
from accounts.models import User
from attendance.calculation_engine import (
    WorkingDaysCalculator,
    AttendanceCappingEngine,
)

logger = logging.getLogger(__name__)


class PayrollPeriod(models.Model):
    """Payroll period supporting both monthly and semi-monthly options."""
    
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        EDITED = 'EDITED', 'Payslips Edited'
        GENERATED = 'GENERATED', 'Generated'
        RELEASED = 'RELEASED', 'Released'
    
    class PeriodType(models.TextChoices):
        SEMI_FIRST = 'SEMI_FIRST', 'First Half'
        SEMI_SECOND = 'SEMI_SECOND', 'Second Half'
    
    month = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    year = models.PositiveIntegerField(
        validators=[MinValueValidator(2020), MaxValueValidator(2100)]
    )
    period_type = models.CharField(
        max_length=20,
        choices=PeriodType.choices,
        default=PeriodType.SEMI_FIRST,
        help_text='Select the first half (1-15) or second half (16-EOMonth)'
    )
    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payroll_periods',
        help_text='Branch covered by this payroll period; blank means all branches.',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True, help_text='When payslips were last edited')
    generated_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    released_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='released_payrolls'
    )
    
    # Period summary totals used by admin listings and payroll reporting.
    total_gross = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0'),
        help_text='Total gross pay for this period'
    )
    total_deductions = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0'),
        help_text='Total deductions for this period'
    )
    total_net = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0'),
        help_text='Total net pay for this period'
    )
    employee_count = models.PositiveIntegerField(
        default=0,
        help_text='Number of employees processed in this period'
    )
    
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-year', '-month', '-period_type']
        indexes = [
            models.Index(fields=['year', 'month']),
            models.Index(fields=['status']),
            models.Index(fields=['period_type']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['month', 'year', 'period_type', 'branch'],
                name='unique_payroll_period_by_type_and_branch',
            ),
        ]
    
    def __str__(self):
        return f"{self.month_name} {self.year} - {self.get_period_type_display()}"
    
    @property
    def month_name(self):
        return date(self.year, self.month, 1).strftime('%B')
    
    @property
    def period_display(self):
        return f"{self.month_name} {self.year} - {self.get_period_type_display()}"

    @property
    def scope_display(self):
        return self.branch.name if self.branch else 'All Branches'
    
    @property
    def days_in_month(self):
        return calendar.monthrange(self.year, self.month)[1]
    
    def get_period_start_end_dates(self):
        """
        Get the start and end dates for this payroll period.
        
        Split based on actual days in the month for fair division:
        - Months with 28 days: First half = 1-14, Second half = 15-28
        - Months with 30 days: First half = 1-15, Second half = 16-30
        - Months with 31 days: First half = 1-16, Second half = 17-31
        
        Returns:
            tuple: (start_date, end_date) as date objects
            
        Examples:
            MONTHLY (Feb 28d): (2026-02-01, 2026-02-28)
            SEMI_FIRST (Feb 28d): (2026-02-01, 2026-02-14)
            SEMI_SECOND (Feb 28d): (2026-02-15, 2026-02-28)
            
            SEMI_FIRST (31-day month): (2026-08-01, 2026-08-16)
            SEMI_SECOND (31-day month): (2026-08-17, 2026-08-31)
        """
        first_day = date(self.year, self.month, 1)
        last_day = date(self.year, self.month, self.days_in_month)
        
        # The clinic operates on semi-monthly payroll only.
        # The first half keeps the odd count when there is one; the second half starts on the even boundary.
        # This makes 31-day months split as 1-15 / 16-31, 30-day as 1-15 / 16-30, and 28-day as 1-14 / 15-28.
        split_day = self.days_in_month // 2

        if self.period_type == self.PeriodType.SEMI_FIRST:
            return (first_day, date(self.year, self.month, split_day))
        elif self.period_type == self.PeriodType.SEMI_SECOND:
            return (date(self.year, self.month, split_day + 1), last_day)
        
        return (first_day, last_day)  # Fallback
    
    def get_working_days_in_period(self):
        """
        Calculate working days (Mon-Fri) in this payroll period.
        Excludes weekends.
        """
        start_date, end_date = self.get_period_start_end_dates()
        working_days = 0
        current = start_date
        
        while current <= end_date:
            if current.weekday() < 5:  # Monday=0, Friday=4
                working_days += 1
            current += timedelta(days=1)
        
        return working_days
    
    def update_totals(self):
        """Recalculate totals from all payslips. Defensive with error handling."""
        try:
            stats = self.payslips.aggregate(
                total_gross=Sum('gross_pay'),
                total_deductions=Sum('total_deductions'),
                total_net=Sum('net_pay'),
                count=Sum('id', output_field=models.IntegerField())  # Count using aggregate
            )
            self.total_gross = stats.get('total_gross') or Decimal('0')
            self.total_deductions = stats.get('total_deductions') or Decimal('0')
            self.total_net = stats.get('total_net') or Decimal('0')
            # Count is None if no payslips, so use 0
            payslip_count = self.payslips.count()
            self.employee_count = payslip_count
            self.save(update_fields=['total_gross', 'total_deductions', 'total_net', 'employee_count'])
        except Exception as e:
            # Log error but don't raise - allow payroll to continue
            import logging
            logger = logging.getLogger('fmh')
            logger.warning(f"Error updating totals for {self}: {e}")


class Payslip(models.Model):
    """
    Individual payslip for an employee.
    
    Simple structure:
    - Base Salary (from employee record)
    - Allowances (overtime, bonus, etc.)
    - Deductions (SSS, PhilHealth, PAG-IBIG, absences, late, cash advance)
    - Net Pay = Base Salary + Allowances - Deductions
    """
    
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        APPROVED = 'APPROVED', 'Approved'
        RELEASED = 'RELEASED', 'Released'
    
    payroll_period = models.ForeignKey(
        PayrollPeriod,
        on_delete=models.CASCADE,
        related_name='payslips'
    )
    employee = models.ForeignKey(
        StaffMember,
        on_delete=models.CASCADE,
        related_name='payslips'
    )
    
    # ─────────── BASE PAY ───────────
    base_salary = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text='Monthly base salary'
    )
    days_worked = models.PositiveIntegerField(default=0)
    days_absent = models.PositiveIntegerField(default=0)
    working_days = models.PositiveIntegerField(default=0)
    sick_hours = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    leave_hours = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    daily_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # ─────────── REST DAYS & LEAVES (From Biometrics) ───────────
    rest_days_mandatory = models.PositiveIntegerField(
        default=4,
        help_text='Mandatory rest days per month (client requirement: minimum 4)'
    )
    paid_leave_type = models.CharField(
        max_length=50,
        default='Sick Leave',
        blank=True,
        help_text='Paid leave category for the current payslip'
    )
    paid_leave_days = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text='Paid leave days used; this reduces the absences count before deduction'
    )
    rest_days_actual = models.PositiveIntegerField(
        default=0,
        help_text='Actual rest days from attendance data'
    )
    sick_leave_days = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text='Sick leave days (PAID - not deducted from salary)'
    )
    regular_leave_days = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text='Regular leave days exceeding rest day allowance (UNPAID - deducted from salary)'
    )
    excess_leave_days = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text='Total leave days exceeding the 4 mandatory rest days (only regular leave counted for deduction)'
    )
    rest_days_exceeded_deduction = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text='Amount deducted due to exceeding 4 mandatory rest days (applies to appropriate period half)'
    )
    
    # ─────────── ALLOWANCES (Earnings) ───────────
    overtime_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    overtime_pay = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    holiday_pay = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    bonus = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    staff_allowance = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('2000'),
        help_text='Monthly staff allowance (split ₱1,000 on 15th + ₱1,000 on 30th)'
    )
    thirteenth_month_pay = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='13th month pay (Philippine labor requirement)'
    )
    
    # ─────────── DEDUCTIONS ───────────
    # Note: SSS, PhilHealth, PagIBIG kept for legacy data but no longer
    # subtracted from employee pay. See clinic_* fields below.
    sss = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    philhealth = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    pagibig = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cash_advance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    late_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    absent_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    other_deductions = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    custom_deductions_total = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text='Total of custom line-item deductions attached to the payslip'
    )
    
    # ─────────── CLINIC-PAID BENEFITS ───────────
    # These are employer-paid contributions, NOT deducted from salary.
    clinic_sss = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='SSS contribution paid by the clinic'
    )
    clinic_philhealth = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='PhilHealth contribution paid by the clinic'
    )
    clinic_pagibig = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='PAG-IBIG contribution paid by the clinic'
    )
    
    # ─────────── TOTALS (calculated) ───────────
    gross_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_allowances = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_clinic_contributions = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text='Total clinic-paid benefits (SSS + PhilHealth + PAG-IBIG)'
    )
    net_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT
    )
    
    # For cash release tracking
    released_at = models.DateTimeField(null=True, blank=True)
    received_by_employee = models.BooleanField(default=False)
    
    notes = models.TextField(blank=True, help_text='Additional notes or remarks')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['payroll_period', 'employee']
        ordering = ['employee__last_name', 'employee__first_name']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['payroll_period', 'status']),
        ]
    
    def __str__(self):
        return f"{self.employee.full_name} - {self.payroll_period.period_display}"
    
    @staticmethod
    def _split_half_period_total(value):
        """Fairly split an integer total across the first and second half of a month.

        The second half gets the remainder when the total is odd, so values like
        27 become 13 and 14, 25 become 12 and 13, and 24 stays 12 and 12.
        """
        value = max(0, int(value))
        first_half = value // 2
        second_half = value - first_half
        return first_half, second_half

    def calculate_raw_absence_days(self):
        """Count only complete 4-punch attendance as worked days; any missing morning/afternoon punch is absent."""
        from attendance.models import DailyAttendance

        period_start, period_end = self.payroll_period.get_period_start_end_dates()

        unique_dates = DailyAttendance.objects.filter(
            staff=self.employee,
            attendance_date__range=[period_start, period_end],
        ).values_list('attendance_date', flat=True).distinct()

        days_worked = 0
        days_absent = 0

        for attendance_date in unique_dates:
            records_for_date = DailyAttendance.objects.filter(
                staff=self.employee,
                attendance_date=attendance_date,
            )

            has_complete_four_punch_day = records_for_date.filter(
                morning_in__isnull=False,
                morning_out__isnull=False,
                afternoon_in__isnull=False,
                afternoon_out__isnull=False,
            ).exists() or records_for_date.filter(four_punch_complete=True).exists()

            if has_complete_four_punch_day:
                days_worked += 1
            else:
                days_absent += 1

        return days_worked, days_absent

    def calculate(self):
        """Calculate all totals based on current values."""
        custom_total = self.custom_deductions_total or Decimal('0')
        if self.pk:
            custom_total = self.custom_deductions.aggregate(
                total=Sum('amount')
            ).get('total') or Decimal('0')
        elif hasattr(self, '_default_custom_deductions'):
            for deduction in getattr(self, '_default_custom_deductions', []):
                try:
                    custom_total += Decimal(str(deduction.get('amount', 0) or 0))
                except Exception:
                    continue
        self.custom_deductions_total = custom_total

        # Total allowances (includes staff allowance)
        self.total_allowances = (
            self.overtime_pay + 
            self.holiday_pay + 
            self.bonus +
            self.staff_allowance +
            self.thirteenth_month_pay
        )
        
        # Total deductions (includes rest days exceeded deduction)
        self.total_deductions = (
            self.sss +
            self.philhealth +
            self.pagibig +
            self.cash_advance + 
            self.late_deduction + 
            self.absent_deduction + 
            self.other_deductions +
            self.rest_days_exceeded_deduction +
            self.custom_deductions_total
        )
        
        # Clinic-paid contributions (informational)
        self.total_clinic_contributions = (
            self.clinic_sss +
            self.clinic_philhealth +
            self.clinic_pagibig
        )
        
        # Gross pay
        self.gross_pay = self.base_salary + self.total_allowances
        
        # Net pay
        self.net_pay = self.gross_pay - self.total_deductions
        
        return self
    
    @property
    def staff_allowance_15th(self):
        """Allowance portion paid on the 15th."""
        return self.staff_allowance / Decimal('2')
    
    @property
    def staff_allowance_30th(self):
        """Allowance portion paid on the 30th."""
        return self.staff_allowance / Decimal('2')
    
    def generate_from_employee(self):
        """
        Auto-generate payslip data from employee record and attendance data.
        
        KEY CHANGES (2026-08-29):
        1. Working days are fetched from MonthlyAttendanceSummary (imported biometrics)
        2. Absence days are imported from biometrics (cannot differentiate type)
        3. User MANUALLY categorizes absences as sick leave or regular leave in payslip edit
        4. Only regular leave exceeding 4 mandatory rest days is deducted from salary
        5. Sick leave is never deducted (counts as paid leave)
        6. Deductions apply to the specific period half where the absence occurred
        """
        from settings.utils import get_setting
        from attendance.models import DailyAttendance, MonthlyAttendanceSummary
        
        monthly_salary = Decimal(str(self.employee.salary or 0))
        is_semi_monthly = self.payroll_period.period_type in [
            self.payroll_period.PeriodType.SEMI_FIRST,
            self.payroll_period.PeriodType.SEMI_SECOND,
        ]
        salary_fraction = Decimal('0.5') if is_semi_monthly else Decimal('1')
        self.base_salary = monthly_salary * salary_fraction

        default_rest_days = int(get_setting('payroll_default_rest_days', 4))
        default_overtime_pay = Decimal(str(get_setting('payroll_default_overtime_pay_per_hour', 0)))

        period_start, period_end = self.payroll_period.get_period_start_end_dates()
        attendance_summary = MonthlyAttendanceSummary.objects.filter(
            staff=self.employee,
            period_start__year=self.payroll_period.year,
            period_start__month=self.payroll_period.month,
        ).first()

        raw_rows = DailyAttendance.objects.filter(
            staff=self.employee,
            attendance_date__range=[period_start, period_end],
        )
        days_worked_from_raw, days_absent_from_raw = self.calculate_raw_absence_days()
        has_any_raw_rows = raw_rows.exists()
        has_any_raw_time_metadata = raw_rows.filter(
            Q(check_in__isnull=False)
            | Q(check_out__isnull=False)
            | Q(morning_in__isnull=False)
            | Q(morning_out__isnull=False)
            | Q(afternoon_in__isnull=False)
            | Q(afternoon_out__isnull=False)
            | Q(four_punch_complete=True)
        ).exists()
        has_complete_raw_pair = raw_rows.filter(
            morning_in__isnull=False,
            morning_out__isnull=False,
            afternoon_in__isnull=False,
            afternoon_out__isnull=False,
        ).exists() or raw_rows.filter(four_punch_complete=True).exists()

        if has_any_raw_rows and has_any_raw_time_metadata:
            # Priority: Use raw DailyAttendance time metadata
            if has_complete_raw_pair:
                # Calculate required days for this period
                required_working_days = WorkingDaysCalculator.calculate_required_working_days(
                    self.payroll_period.year,
                    self.payroll_period.month,
                    self.payroll_period.period_type,
                    default_rest_days,
                )
                
                # Apply capping: MIN(calculated_attendance, required_working_days)
                capping_engine = AttendanceCappingEngine()
                capped_working_days, capping_note = capping_engine.cap_attendance_days(
                    days_worked_from_raw, required_working_days
                )
                
                if capping_note:
                    logger.warning(f"Attendance capping for {self.employee.full_name}: {capping_note}")
                
                # working_days = required days available in period (after rest day deduction)
                # days_worked = actual attendance (capped)
                # days_absent = required - actual
                self.working_days = required_working_days
                self.days_worked = max(0, capped_working_days)
                self.days_absent = max(0, required_working_days - capped_working_days)
                self.rest_days_actual = default_rest_days
                working_days_for_half = self.working_days
            else:
                # No complete pairs found - calculate required days and absences correctly
                required_working_days = WorkingDaysCalculator.calculate_required_working_days(
                    self.payroll_period.year,
                    self.payroll_period.month,
                    self.payroll_period.period_type,
                    default_rest_days,
                )
                
                # working_days = required days available in period (after rest day deduction)
                # days_worked = 0 (no attendance)
                # days_absent = required days (all absent)
                self.working_days = required_working_days
                self.days_worked = 0
                self.days_absent = max(0, required_working_days)
                self.rest_days_actual = default_rest_days
                working_days_for_half = self.working_days
        else:
            # Fallback: Use MonthlyAttendanceSummary data
            # Note: working_days = calendar working days in month (not actual worked)
            #       attendance_days = actual days with attendance (from biometric file)
            summary_working_days = attendance_summary.working_days if attendance_summary else 0
            summary_attendance_days = getattr(attendance_summary, 'attendance_days', 0) or 0
            summary_absence_days = getattr(attendance_summary, 'absence_days', 0) or 0

            if attendance_summary:
                # Calculate required working days for this period
                required_working_days = WorkingDaysCalculator.calculate_required_working_days(
                    self.payroll_period.year,
                    self.payroll_period.month,
                    self.payroll_period.period_type,
                    default_rest_days,
                )
                
                # For semi-monthly payroll, split the full-month values
                if is_semi_monthly:
                    # Split calendar days for reference
                    if summary_working_days > 0:
                        first_half, second_half = self._split_half_period_total(summary_working_days)
                        summary_working_days = first_half if self.payroll_period.period_type == self.payroll_period.PeriodType.SEMI_FIRST else second_half
                    
                    # Split actual attendance days for capping calculation
                    if summary_attendance_days > 0:
                        first_half, second_half = self._split_half_period_total(summary_attendance_days)
                        summary_attendance_days = first_half if self.payroll_period.period_type == self.payroll_period.PeriodType.SEMI_FIRST else second_half
                
                # Apply attendance capping: MIN(actual_attendance, required_working_days)
                # Use attendance_days (actual worked) not working_days (calendar days)
                capping_engine = AttendanceCappingEngine()
                capped_working_days, capping_note = capping_engine.cap_attendance_days(
                    summary_attendance_days, required_working_days
                )
                
                if capping_note:
                    logger.warning(f"Attendance capping for {self.employee.full_name}: {capping_note}")
                
                # working_days = required days available in period (after rest day deduction)
                # days_worked = actual attendance (capped)
                # days_absent = required - actual
                self.working_days = required_working_days
                self.days_worked = max(0, capped_working_days)
                self.days_absent = max(0, required_working_days - capped_working_days)
                self.rest_days_actual = default_rest_days
                working_days_for_half = self.working_days
            else:
                # No summary data exists; calculate required working days from formula
                required_working_days = WorkingDaysCalculator.calculate_required_working_days(
                    self.payroll_period.year,
                    self.payroll_period.month,
                    self.payroll_period.period_type,
                    default_rest_days,
                )
                
                # working_days = required days available in period (after rest day deduction)
                # days_worked = 0 (no attendance data)
                # days_absent = required days (all absent)
                self.working_days = required_working_days
                self.days_worked = 0
                self.days_absent = max(0, required_working_days)
                self.rest_days_actual = default_rest_days
                working_days_for_half = self.working_days

        self.daily_salary = (
            self.base_salary / Decimal(str(working_days_for_half))
            if self.base_salary and working_days_for_half > 0 else Decimal('0')
        )

        self.sick_hours = Decimal('0')
        self.sick_leave_days = Decimal('0')
        self.leave_hours = Decimal('0')
        self.regular_leave_days = Decimal('0')

        self.rest_days_mandatory = default_rest_days
        self.excess_leave_days = Decimal('0')
        self.rest_days_exceeded_deduction = Decimal('0')

        default_absent_deduction = Decimal(str(get_setting('payroll_default_absent_deduction', 100)))
        effective_absent_days = max(0, int(self.days_absent) - int(self.paid_leave_days)) if self.paid_leave_days else int(self.days_absent)
        self.absent_deduction = Decimal(str(effective_absent_days)) * default_absent_deduction

        default_staff_allowance = get_setting('payroll_default_staff_allowance', 2000)
        emp_staff_allowance = getattr(self.employee, 'default_staff_allowance', None)
        base_staff_allowance = Decimal(str(emp_staff_allowance or default_staff_allowance))
        self.staff_allowance = base_staff_allowance / Decimal('2') if is_semi_monthly else base_staff_allowance

        required_working_days = WorkingDaysCalculator.calculate_required_working_days(
            self.payroll_period.year,
            self.payroll_period.month,
            self.payroll_period.period_type,
            default_rest_days,
        )
        eligible_overtime_rows = raw_rows.order_by('attendance_date')[:required_working_days]
        raw_overtime_hours = eligible_overtime_rows.aggregate(total=Sum('ot_hours_calculated'))['total'] or Decimal('0')
        self.overtime_hours = raw_overtime_hours if raw_overtime_hours > 0 else (
            Decimal(str(attendance_summary.overtime_hours)) if attendance_summary else Decimal('0')
        )
        self.overtime_pay = default_overtime_pay
        
        default_custom_deductions = getattr(self.employee, 'default_custom_deductions', None) or []
        
        # Zero out legacy deduction fields and clinic-paid contributions first
        self.sss = Decimal('0')
        self.philhealth = Decimal('0')
        self.pagibig = Decimal('0')
        self.tax = Decimal('0')
        self.clinic_sss = Decimal('0')
        self.clinic_philhealth = Decimal('0')
        self.clinic_pagibig = Decimal('0')

        # Calculate statutory contributions based on settings (clinic-paid, not deducted from salary)
        auto_statutory = get_setting('payroll_auto_statutory', True)

        if auto_statutory and self.base_salary > 0:
            # SSS
            if get_setting('payroll_enable_sss', True):
                sss_rate = Decimal(str(get_setting('payroll_sss_rate', 4.50)))
                self.clinic_sss = self.base_salary * (sss_rate / Decimal('100'))

            # PhilHealth
            if get_setting('payroll_enable_philhealth', True):
                ph_rate = Decimal(str(get_setting('payroll_philhealth_rate', 2.00)))
                self.clinic_philhealth = self.base_salary * (ph_rate / Decimal('100'))

            # Pag-IBIG
            if get_setting('payroll_enable_pagibig', True):
                self.clinic_pagibig = Decimal(str(get_setting('payroll_pagibig_fixed', 100)))

        # Keep default custom deductions available for the caller to persist
        # after the payslip is saved.
        self._default_custom_deductions = [
            {
                'reason': str(deduction.get('reason', '')).strip(),
                'amount': str(deduction.get('amount', 0) or 0),
            }
            for deduction in default_custom_deductions
            if str(deduction.get('reason', '')).strip()
        ]

        # Calculate totals
        self.calculate()
        
        return self
    
    @property
    def daily_rate(self):
        """
        Calculate daily rate based only on actual working days from biometric data.
        If no attendance summary exists, this must stay at zero.
        """
        from attendance.models import MonthlyAttendanceSummary

        attendance_summary = MonthlyAttendanceSummary.objects.filter(
            staff=self.employee,
            period_start__year=self.payroll_period.year,
            period_start__month=self.payroll_period.month,
        ).first()

        working_days = attendance_summary.working_days if attendance_summary and attendance_summary.working_days > 0 else 0

        if self.payroll_period.period_type in [
            self.payroll_period.PeriodType.SEMI_FIRST,
            self.payroll_period.PeriodType.SEMI_SECOND,
        ] and working_days > 0:
            first_half, second_half = self._split_half_period_total(working_days)
            working_days = first_half if self.payroll_period.period_type == self.payroll_period.PeriodType.SEMI_FIRST else second_half
            working_days = max(1, working_days)

        if self.base_salary > 0 and working_days > 0:
            return self.base_salary / Decimal(str(working_days))
        return Decimal('0')


class PayslipDeduction(models.Model):
    """Custom line-item deduction attached to a payslip."""

    payslip = models.ForeignKey(
        Payslip,
        on_delete=models.CASCADE,
        related_name='custom_deductions'
    )
    reason = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.reason} - ₱{self.amount}'


# ═══════════════════════════════════════════════════════════════════
#                           AUDIT LOG
# ═══════════════════════════════════════════════════════════════════

class PayrollAuditLog(models.Model):
    """
    Comprehensive audit trail for all payroll system actions.
    Tracks who did what, when, and to which record.
    """
    
    class ActionType(models.TextChoices):
        # Payroll Period Actions
        PERIOD_CREATED = 'PERIOD_CREATED', 'Period Created'
        PERIOD_GENERATED = 'PERIOD_GENERATED', 'Payslips Generated'
        PERIOD_RELEASED = 'PERIOD_RELEASED', 'Payroll Released'
        PERIOD_DELETED = 'PERIOD_DELETED', 'Period Deleted'
        
        # Payslip Actions
        PAYSLIP_CREATED = 'PAYSLIP_CREATED', 'Payslip Created'
        PAYSLIP_EDITED = 'PAYSLIP_EDITED', 'Payslip Edited'
        PAYSLIP_APPROVED = 'PAYSLIP_APPROVED', 'Payslip Approved'
        PAYSLIP_SENT = 'PAYSLIP_SENT', 'Payslip Sent'
        PAYSLIP_DELETED = 'PAYSLIP_DELETED', 'Payslip Deleted'
        
        # Vet/Staff Actions
        VET_SALARY_UPDATED = 'VET_SALARY_UPDATED', 'Vet Salary Updated'
        VET_BONUS_ADDED = 'VET_BONUS_ADDED', 'Bonus Added'
        VET_DEDUCTION_ADDED = 'VET_DEDUCTION_ADDED', 'Deduction Added'
        
        # System Actions
        SYSTEM_LOGIN = 'SYSTEM_LOGIN', 'Admin Login'
        SYSTEM_EXPORT = 'SYSTEM_EXPORT', 'Data Exported'
    
    # Who performed the action
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='payroll_audit_logs'
    )
    
    # What action was performed
    action_type = models.CharField(
        max_length=30,
        choices=ActionType.choices
    )
    
    # Human-readable description
    description = models.TextField()
    
    # Related records (optional - for linking to specific items)
    payroll_period = models.ForeignKey(
        PayrollPeriod,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs'
    )
    payslip = models.ForeignKey(
        Payslip,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs'
    )
    staff_member = models.ForeignKey(
        StaffMember,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payroll_audit_logs'
    )
    
    # Store additional context as JSON
    metadata = models.JSONField(default=dict, blank=True)
    
    # IP Address for security tracking
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    # Timestamp
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Payroll Audit Log'
        verbose_name_plural = 'Payroll Audit Logs'
    
    def __str__(self):
        return f"[{self.created_at.strftime('%Y-%m-%d %H:%M')}] {self.get_action_type_display()} by {self.user}"
    
    @classmethod
    def log(cls, user, action_type, description, **kwargs):
        """
        Convenience method to create an audit log entry.
        
        Usage:
            PayrollAuditLog.log(
                user=request.user,
                action_type=PayrollAuditLog.ActionType.PAYSLIP_EDITED,
                description=f"Edited payslip for {employee.full_name}",
                payslip=payslip,
                metadata={'old_value': 1000, 'new_value': 1200}
            )
        """
        return cls.objects.create(
            user=user,
            action_type=action_type,
            description=description,
            **kwargs
        )


class StatutoryDeductionTable(models.Model):
    """Philippine statutory deduction brackets for SSS, PhilHealth, PAG-IBIG, etc."""
    
    class DeductionType(models.TextChoices):
        SSS = 'SSS', 'SSS'
        PHILHEALTH = 'PHILHEALTH', 'PhilHealth'
        PAGIBIG = 'PAGIBIG', 'PAG-IBIG'
        TAX = 'TAX', 'Income Tax'
    
    deduction_type = models.CharField(max_length=20, choices=DeductionType.choices)
    min_salary = models.DecimalField(max_digits=12, decimal_places=2)
    max_salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    employee_rate = models.DecimalField(max_digits=5, decimal_places=4, default=0)
    employer_rate = models.DecimalField(max_digits=5, decimal_places=4, default=0)
    fixed_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    effective_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    
    class Meta:
        ordering = ['deduction_type', 'min_salary']
        verbose_name = 'Statutory Deduction Table'
        verbose_name_plural = 'Statutory Deduction Tables'
    
    def __str__(self):
        if self.max_salary:
            return f"{self.get_deduction_type_display()} - ₱{self.min_salary}-₱{self.max_salary}"
        else:
            return f"{self.get_deduction_type_display()} - ₱{self.min_salary}+"


class PayslipEmailLog(models.Model):
    """Track email sends for audit and re-send capabilities."""
    
    payslip = models.ForeignKey(
        Payslip,
        on_delete=models.CASCADE,
        related_name='email_logs'
    )
    recipient_email = models.EmailField()
    sent_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('SENT', 'Sent'),
            ('FAILED', 'Failed'),
            ('BOUNCED', 'Bounced'),
        ],
        default='SENT'
    )
    error_message = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-sent_at']
        constraints = [
            models.UniqueConstraint(
                fields=['payslip', 'recipient_email'],
                condition=models.Q(status='SENT'),
                name='unique_successful_payslip_email',
            ),
        ]
    
    def __str__(self):
        return f"{self.payslip} → {self.recipient_email} ({self.status})"
