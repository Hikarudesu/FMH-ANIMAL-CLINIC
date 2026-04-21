"""
Simplified Payroll Models for FMH Animal Clinic.

Simple flow:
1. Select payroll period (month/year)
2. Generate payslips for all active employees
3. Review and approve payslips
4. Mark as released (cash payment)
5. Print payslips for distribution
"""
from decimal import Decimal
from datetime import date
import calendar

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from employees.models import StaffMember
from accounts.models import User


class PayrollPeriod(models.Model):
    """Monthly payroll period - tracks when payroll was processed."""
    
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        GENERATED = 'GENERATED', 'Generated'
        RELEASED = 'RELEASED', 'Released'
    
    month = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    year = models.PositiveIntegerField(
        validators=[MinValueValidator(2020), MaxValueValidator(2100)]
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT
    )
    
    # Summary totals (calculated when payslips are generated)
    total_gross = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_deductions = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_net = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    employee_count = models.PositiveIntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    generated_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    released_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='released_payrolls'
    )
    
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-year', '-month']
        unique_together = ['month', 'year']
        indexes = [
            models.Index(fields=['year', 'month']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.month_name} {self.year}"
    
    @property
    def month_name(self):
        return date(self.year, self.month, 1).strftime('%B')
    
    @property
    def period_display(self):
        return f"{self.month_name} {self.year}"
    
    @property
    def days_in_month(self):
        return calendar.monthrange(self.year, self.month)[1]
    
    def update_totals(self):
        """Recalculate totals from all payslips."""
        from django.db.models import Sum, Count
        stats = self.payslips.aggregate(
            total_gross=Sum('gross_pay'),
            total_deductions=Sum('total_deductions'),
            total_net=Sum('net_pay'),
            count=Count('id')
        )
        self.total_gross = stats['total_gross'] or 0
        self.total_deductions = stats['total_deductions'] or 0
        self.total_net = stats['total_net'] or 0
        self.employee_count = stats['count'] or 0
        self.save()


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
    
    # ─────────── ALLOWANCES (Earnings) ───────────
    overtime_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    overtime_pay = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    holiday_pay = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    bonus = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    allowance = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='Other allowances (transportation, meal, etc.)'
    )
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
        # Total allowances (includes staff allowance)
        self.total_allowances = (
            self.overtime_pay + 
            self.holiday_pay + 
            self.bonus + 
            self.allowance +
            self.staff_allowance +
            self.thirteenth_month_pay
        )
        
        # Total deductions
        self.total_deductions = (
            self.sss +
            self.philhealth +
            self.pagibig +
            self.tax +
            self.cash_advance + 
            self.late_deduction + 
            self.absent_deduction + 
            self.other_deductions
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
        Auto-generate payslip data from employee record.
        Reads configurable defaults from system settings.
        Statutory contributions are clinic-paid (not deducted from salary)
        and only calculated when enabled in settings.
        """
        from settings.utils import get_setting
        
        # Get base salary from employee
        self.base_salary = Decimal(str(self.employee.salary or 0))
        
        # Use configurable default work days from settings
        default_days = get_setting('payroll_default_work_days', 22)
        self.days_worked = getattr(self.employee, 'default_days_worked', None) or int(default_days)
        self.days_absent = 0
        
        # Staff allowance from employee defaults, falling back to settings default
        default_staff_allowance = get_setting('payroll_default_staff_allowance', 2000)
        emp_staff_allowance = getattr(self.employee, 'default_staff_allowance', None)
        self.staff_allowance = Decimal(str(emp_staff_allowance or default_staff_allowance))
        
        # Other allowances from employee defaults
        default_other_allowance = getattr(self.employee, 'default_other_allowance', None)
        self.allowance = Decimal(str(default_other_allowance or 0))
        
        # Zero out legacy deduction fields
        self.sss = Decimal('0')
        self.philhealth = Decimal('0')
        # Calculate statutory contributions based on settings
        auto_statutory = get_setting('payroll_auto_statutory', True)
        
        if auto_statutory and self.base_salary > 0:
            # SSS
            if get_setting('payroll_enable_sss', True):
                sss_rate = Decimal(str(get_setting('payroll_sss_rate', 4.50)))
                self.sss = self.base_salary * (sss_rate / Decimal('100'))
            else:
                self.sss = Decimal('0')
            
            # PhilHealth
            if get_setting('payroll_enable_philhealth', True):
                ph_rate = Decimal(str(get_setting('payroll_philhealth_rate', 2.00)))
                self.philhealth = self.base_salary * (ph_rate / Decimal('100'))
            else:
                self.philhealth = Decimal('0')
            
            # Pag-IBIG
            if get_setting('payroll_enable_pagibig', True):
                self.pagibig = Decimal(str(get_setting('payroll_pagibig_fixed', 100)))
            else:
                self.pagibig = Decimal('0')
        else:
            # Statutory disabled — zero out everything
            self.sss = Decimal('0')
            self.philhealth = Decimal('0')
            self.pagibig = Decimal('0')
            
        self.clinic_sss = Decimal('0')
        self.clinic_philhealth = Decimal('0')
        self.clinic_pagibig = Decimal('0')
        
        # Calculate totals
        self.calculate()
        
        return self
    
    @property
    def daily_rate(self):
        """Calculate daily rate based on 22 working days."""
        if self.base_salary > 0:
            return self.base_salary / Decimal('22')
        return Decimal('0')


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
