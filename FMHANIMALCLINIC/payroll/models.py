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
from decimal import Decimal
from datetime import date, timedelta
import calendar

from django.db import models
from django.db.models import Q, Sum
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from employees.models import StaffMember
from accounts.models import User


class PayrollPeriod(models.Model):
    """Payroll period supporting first-half and second-half payrolls."""
    
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
            SEMI_FIRST (Feb 28d): (2026-02-01, 2026-02-14)
            SEMI_SECOND (Feb 28d): (2026-02-15, 2026-02-28)
            
            SEMI_FIRST (31-day month): (2026-08-01, 2026-08-16)
            SEMI_SECOND (31-day month): (2026-08-17, 2026-08-31)
        """
        first_day = date(self.year, self.month, 1)
        last_day = date(self.year, self.month, self.days_in_month)
        
        # Calculate mid-point based on days in month
        # For equal division: mid_point = (days_in_month // 2) + 1
        # This ensures first half is always <= second half
        mid_point = self.days_in_month // 2
        
        if self.period_type == self.PeriodType.SEMI_FIRST:
            return (first_day, date(self.year, self.month, mid_point))
        elif self.period_type == self.PeriodType.SEMI_SECOND:
            return (date(self.year, self.month, mid_point + 1), last_day)
        
        return (first_day, date(self.year, self.month, self.days_in_month))
    
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
        help_text='Staff allowance for this half-month payroll period'
    )
    thirteenth_month_pay = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='13th month pay (Philippine labor requirement)'
    )
    
    # ─────────── DEDUCTIONS ───────────
    # Employee statutory deductions, controlled by Payroll Settings.
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
    
    def calculate(self):
        """Calculate all totals based on current values."""
        from settings.utils import get_setting

        # Statutory deductions are employee deductions when enabled in payroll settings.
        self.sss = Decimal('0')
        self.philhealth = Decimal('0')
        self.pagibig = Decimal('0')
        auto_statutory = get_setting('payroll_auto_statutory', True)
        statutory_fraction = Decimal('0.5')
        if auto_statutory and self.base_salary > 0:
            if get_setting('payroll_enable_sss', True):
                self.sss = self.base_salary * (
                    Decimal(str(get_setting('payroll_sss_rate', 4.50)))
                    * statutory_fraction / Decimal('100')
                )
            if get_setting('payroll_enable_philhealth', True):
                self.philhealth = self.base_salary * (
                    Decimal(str(get_setting('payroll_philhealth_rate', 2.00)))
                    * statutory_fraction / Decimal('100')
                )
            if get_setting('payroll_enable_pagibig', True):
                self.pagibig = Decimal(str(get_setting('payroll_pagibig_fixed', 100))) * statutory_fraction

        self.sss = self.sss.quantize(Decimal('0.01'))
        self.philhealth = self.philhealth.quantize(Decimal('0.01'))
        self.pagibig = self.pagibig.quantize(Decimal('0.01'))

        # Absence deductions always follow the current attendance and daily salary.
        paid_leave_days = self.paid_leave_days or Decimal('0')
        unpaid_absence_days = max(
            Decimal('0'),
            Decimal(str(self.days_absent or 0)) - paid_leave_days,
        )
        self.absent_deduction = (
            unpaid_absence_days * (self.daily_salary or Decimal('0'))
        ).quantize(Decimal('0.01'))

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
        
        # Keep the legacy clinic contribution total synchronized for old reports.
        self.total_clinic_contributions = (
            self.sss + self.philhealth + self.pagibig
        )
        
        # Gross pay
        self.gross_pay = self.base_salary + self.total_allowances
        
        # Net pay
        self.net_pay = self.gross_pay - self.total_deductions
        
        return self
    
    @property
    def staff_allowance_15th(self):
        """Allowance portion paid on the 15th."""
        return self.staff_allowance
    
    @property
    def staff_allowance_30th(self):
        """Allowance portion paid on the 30th."""
        return self.staff_allowance
    
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
        from attendance.calculation_engine import WorkingDaysCalculator
        
        # Employee salary is monthly and each payroll period pays one half.
        monthly_salary = Decimal(str(self.employee.salary or 0))
        self.base_salary = monthly_salary * Decimal('0.5')
        
        # Fetch attendance data from biometric import for this period
        period_start, period_end = self.payroll_period.get_period_start_end_dates()
        attendance_summary = MonthlyAttendanceSummary.objects.filter(
            staff=self.employee,
            period_start__year=self.payroll_period.year,
            period_start__month=self.payroll_period.month,
        ).first()
        
        self.rest_days_mandatory = int(get_setting('payroll_default_rest_days', 4))
        working_days_for_half = WorkingDaysCalculator.calculate_required_working_days(
            self.payroll_period.year,
            self.payroll_period.month,
            self.payroll_period.period_type,
            self.rest_days_mandatory,
        )

        daily_records = DailyAttendance.objects.filter(
            staff=self.employee,
            attendance_date__range=[period_start, period_end],
        )
        has_detailed_punches = daily_records.filter(
            Q(morning_in__isnull=False)
            | Q(morning_out__isnull=False)
            | Q(afternoon_in__isnull=False)
            | Q(afternoon_out__isnull=False)
        ).exists()
        if has_detailed_punches:
            complete_attendance_days = daily_records.filter(
                morning_in__isnull=False,
                morning_out__isnull=False,
                afternoon_in__isnull=False,
                afternoon_out__isnull=False,
            ).count()
        else:
            complete_attendance_days = (
                attendance_summary.attendance_days if attendance_summary else 0
            )

        self.working_days = working_days_for_half
        self.days_worked = min(complete_attendance_days, working_days_for_half)
        self.days_absent = max(0, working_days_for_half - self.days_worked)

        # Calculate daily salary based on base salary and the actual working days in-range.
        # When no attendance summary exists, working_days_for_half stays at zero.
        self.daily_salary = (
            self.base_salary / Decimal(str(working_days_for_half))
            if self.base_salary and working_days_for_half > 0 else Decimal('0')
        )
        self.absent_deduction = (
            Decimal(str(self.days_absent)) * self.daily_salary
        ).quantize(Decimal('0.01'))

        # ─────────── POPULATE ABSENCE DATA FROM BIOMETRICS ───────────
        # NOTE: Biometric data cannot differentiate between sick leave and regular leave
        # User will manually categorize these in the payslip edit form.
        # When no attendance import exists, leave everything at zero.
        if attendance_summary:
            self.rest_days_actual = min(
                int(attendance_summary.absence_days or 0),
                self.rest_days_mandatory,
            )
        else:
            self.rest_days_actual = 0
        
        # Initialize leave fields as ZERO - user will manually enter in edit form
        self.sick_hours = Decimal('0')
        self.sick_leave_days = Decimal('0')
        self.leave_hours = Decimal('0')
        self.regular_leave_days = Decimal('0')
        
        # ─────────── CALCULATE REST DAYS EXCEEDED DEDUCTION ───────────
        # Logic: If actual rest days exceed the configured default, excess days are deducted
        # BUT user must specify which absences are regular leave vs sick leave in edit form.
        # The default is configurable in payroll settings and must stay at 4 unless changed.
        if self.rest_days_actual > self.rest_days_mandatory:
            # Excess days exist, but user will specify the breakdown in edit form
            self.excess_leave_days = Decimal('0')  # Will be calculated when user edits
            self.rest_days_exceeded_deduction = Decimal('0')  # Will be calculated when user edits
        else:
            # No excess
            self.excess_leave_days = Decimal('0')
            self.rest_days_exceeded_deduction = Decimal('0')
        
        # Staff allowance from employee defaults, falling back to settings default
        default_staff_allowance = get_setting('payroll_default_staff_allowance', 2000)
        emp_staff_allowance = getattr(self.employee, 'default_staff_allowance', None)
        monthly_staff_allowance = Decimal(str(emp_staff_allowance or default_staff_allowance))
        self.staff_allowance = monthly_staff_allowance / Decimal('2')
        
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
        statutory_fraction = Decimal('0.5')

        if auto_statutory and self.base_salary > 0:
            # SSS
            if get_setting('payroll_enable_sss', True):
                sss_rate = Decimal(str(get_setting('payroll_sss_rate', 4.50))) * statutory_fraction
                self.clinic_sss = self.base_salary * (sss_rate / Decimal('100'))

            # PhilHealth
            if get_setting('payroll_enable_philhealth', True):
                ph_rate = Decimal(str(get_setting('payroll_philhealth_rate', 2.00))) * statutory_fraction
                self.clinic_philhealth = self.base_salary * (ph_rate / Decimal('100'))

            # Pag-IBIG
            if get_setting('payroll_enable_pagibig', True):
                self.clinic_pagibig = Decimal(str(get_setting('payroll_pagibig_fixed', 100))) * statutory_fraction

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
            working_days = max(1, working_days // 2)

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
    
    def __str__(self):
        return f"{self.payslip} → {self.recipient_email} ({self.status})"
