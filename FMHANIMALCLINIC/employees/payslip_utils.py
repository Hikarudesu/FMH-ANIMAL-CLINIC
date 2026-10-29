"""
Payslip computation utilities for the employees app.
"""
from datetime import date
from decimal import Decimal


class PayslipData:
    """Data class to hold computed payslip information."""

    def __init__(self, staff, month, year):
        self.staff = staff
        self.month = month
        self.year = year

    @property
    def period(self):
        """Return the period as a formatted string (e.g., 'March 2026')."""
        return date(self.year, self.month, 1).strftime('%B %Y')


def compute_payslip(staff_member, month, year):
    """
    Compute payslip data for a staff member for a given month/year.

    Args:
        staff_member: StaffMember model instance
        month: int (1-12)
        year: int (e.g., 2026)

    Returns:
        PayslipData object with computed values
    """
    payslip = PayslipData(staff_member, month, year)

    # Get base salary from staff member
    base_salary = Decimal(str(staff_member.salary or 0))
    payslip.base_salary = base_salary

    # Payroll working days follow the configured monthly rest-day policy.
    from attendance.calculation_engine import WorkingDaysCalculator
    from settings.utils import get_setting

    working_days = WorkingDaysCalculator.calculate_required_working_days(
        year,
        month,
        'FULL_MONTH',
        int(get_setting('payroll_default_rest_days', 4)),
    )

    # Count actual days worked from schedule
    from .models import VetSchedule
    days_worked = VetSchedule.objects.filter(
        staff=staff_member,
        date__year=year,
        date__month=month,
        is_available=True,
    ).values('date').distinct().count()

    # If no schedule entries, assume full working days
    if days_worked == 0:
        days_worked = working_days

    payslip.days_worked = days_worked
    payslip.attendance_days = days_worked
    payslip.working_days = working_days
    payslip.days_absent = max(0, working_days - days_worked)
    payslip.absence_days = payslip.days_absent
    payslip.overtime_hours = Decimal('0')
    payslip.sick_hours = Decimal('0')
    payslip.leave_hours = Decimal('0')
    payslip.overtime_pay = Decimal('0')
    payslip.charges = Decimal('0')

    # Calculate daily rate and gross pay
    daily_rate = base_salary / Decimal(working_days) if working_days > 0 else Decimal(0)
    gross_pay = daily_rate * Decimal(days_worked)

    payslip.daily_rate = round(daily_rate, 2)
    payslip.daily_salary = payslip.daily_rate
    payslip.gross_pay = round(gross_pay, 2)

    # Calculate mandatory contributions (Philippine rates)
    # SSS - approximately 4.5% of gross (employee share)
    sss = gross_pay * Decimal('0.045')
    payslip.sss = round(min(sss, Decimal('1125')), 2)  # Max SSS contribution cap

    # PhilHealth - 2.25% of gross (employee share, as of 2024)
    philhealth = gross_pay * Decimal('0.0225')
    payslip.philhealth = round(min(philhealth, Decimal('2025')), 2)  # Max cap

    # PAG-IBIG - 2% of gross (capped at 100 PHP)
    pagibig = gross_pay * Decimal('0.02')
    payslip.pagibig = round(min(pagibig, Decimal('100')), 2)

    # Total deductions
    payslip.total_deductions = payslip.sss + payslip.philhealth + payslip.pagibig

    # Net pay
    payslip.net_pay = round(payslip.gross_pay - payslip.total_deductions, 2)

    from attendance.models import DailyAttendance, MonthlyAttendanceSummary
    from attendance.services import count_attendance_days_for_payroll

    raw_rows = DailyAttendance.objects.filter(
        staff=staff_member,
        attendance_date__year=year,
        attendance_date__month=month,
    )
    has_raw_time_metadata = raw_rows.filter(
        check_in__isnull=False,
    ).exists() or raw_rows.filter(
        check_out__isnull=False,
    ).exists() or raw_rows.filter(
        morning_in__isnull=False,
    ).exists() or raw_rows.filter(
        morning_out__isnull=False,
    ).exists() or raw_rows.filter(
        afternoon_in__isnull=False,
    ).exists() or raw_rows.filter(
        afternoon_out__isnull=False,
    ).exists()

    monthly_summary = MonthlyAttendanceSummary.objects.filter(
        staff=staff_member,
        period_start__year=year,
        period_start__month=month,
    ).order_by('-period_end').first()
    if has_raw_time_metadata:
        attendance_days = count_attendance_days_for_payroll(
            raw_rows,
            raw_rows,
            monthly_summary,
        )
        payslip.days_worked = min(attendance_days, working_days)
        payslip.attendance_days = payslip.days_worked
        payslip.days_absent = max(0, working_days - payslip.days_worked)
        payslip.absence_days = payslip.days_absent
        payslip.gross_pay = round(daily_rate * Decimal(payslip.days_worked), 2)
        payslip.net_pay = round(payslip.gross_pay - payslip.total_deductions, 2)
    elif monthly_summary:
        payslip.attendance_days = min(monthly_summary.attendance_days, working_days)
        payslip.days_worked = payslip.attendance_days
        payslip.absence_days = max(0, working_days - payslip.days_worked)
        payslip.days_absent = payslip.absence_days
        payslip.overtime_hours = monthly_summary.overtime_hours
        payslip.sick_hours = monthly_summary.sick_hours
        payslip.leave_hours = monthly_summary.leave_hours
        payslip.overtime_pay = monthly_summary.overtime_pay
        payslip.charges = monthly_summary.charges
        payslip.gross_pay = round(daily_rate * Decimal(payslip.days_worked), 2)
        payslip.net_pay = round(payslip.gross_pay - payslip.total_deductions, 2)
        if monthly_summary.real_pay:
            payslip.net_pay = monthly_summary.real_pay

    return payslip
