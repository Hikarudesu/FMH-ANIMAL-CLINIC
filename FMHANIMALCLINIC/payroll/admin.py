from django.contrib import admin
from .models import (
    PayrollPeriod, Payslip, PayrollAuditLog,
    StatutoryDeductionTable, PayslipEmailLog
)


@admin.register(PayrollPeriod)
class PayrollPeriodAdmin(admin.ModelAdmin):
    list_display = ('period_display', 'status', 'employee_count', 'total_gross', 'total_net', 'created_at')
    list_filter = ('status', 'year')
    ordering = ('-year', '-month')


@admin.register(Payslip)
class PayslipAdmin(admin.ModelAdmin):
    list_display = ('employee', 'payroll_period', 'base_salary', 'gross_pay', 'total_deductions', 'net_pay', 'status')
    list_filter = ('status', 'payroll_period')
    search_fields = ('employee__first_name', 'employee__last_name')
    raw_id_fields = ('employee', 'payroll_period')


@admin.register(PayrollAuditLog)
class PayrollAuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'action_type', 'user', 'description')
    list_filter = ('action_type', 'created_at', 'user')
    search_fields = ('description', 'user__username')
    readonly_fields = ('created_at', 'user', 'action_type', 'description', 'ip_address', 'metadata')
    ordering = ('-created_at',)


@admin.register(StatutoryDeductionTable)
class StatutoryDeductionTableAdmin(admin.ModelAdmin):
    list_display = ('deduction_type', 'min_salary', 'max_salary', 'employee_rate', 'effective_date')
    list_filter = ('deduction_type', 'effective_date')
    ordering = ('deduction_type', 'min_salary')


@admin.register(PayslipEmailLog)
class PayslipEmailLogAdmin(admin.ModelAdmin):
    list_display = ('payslip', 'recipient_email', 'status', 'sent_at')
    list_filter = ('status', 'sent_at')
    search_fields = ('recipient_email', 'payslip__employee__first_name')
    readonly_fields = ('sent_at', 'payslip')

