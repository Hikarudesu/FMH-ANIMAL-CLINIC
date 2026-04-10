"""
Payslip computation utilities for the employees app.
"""
from datetime import date
from decimal import Decimal
import calendar


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

    # Calculate working days in the month (excluding weekends)
    _, days_in_month = calendar.monthrange(year, month)
    working_days = sum(
        1 for d in range(1, days_in_month + 1)
        if date(year, month, d).weekday() < 5  # Mon-Fri
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
    payslip.working_days = working_days

    # Calculate daily rate and gross pay
    daily_rate = base_salary / Decimal(working_days) if working_days > 0 else Decimal(0)
    gross_pay = daily_rate * Decimal(days_worked)

    payslip.daily_rate = round(daily_rate, 2)
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

    return payslip
