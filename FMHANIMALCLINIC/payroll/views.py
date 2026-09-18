"""
Simplified Payroll Views for FMH Animal Clinic.

NEW WORKFLOW:
1. Load Period - Select payroll period and semi-monthly option
2. Edit Payslips - Adjust deductions, bonuses, overtime BEFORE calculation
3. Generate Payroll - Lock in calculations with transaction.atomic()
4. Release Payroll - Mark as released and send payslips

Tab Navigation:
- Dashboard: Overview with stats and activity
- Vets: List of employees with payroll history
- Send Payslips: Payroll generation and delivery history
- Payroll Logs: Transaction records of salary disbursements
"""
# pylint: disable=no-member
import logging
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import json

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum, Count
from django.utils import timezone
from django.http import Http404

from accounts.models import User
from accounts.decorators import module_permission_required, special_permission_required
from employees.models import StaffMember
from branches.models import Branch
from payroll.models import PayrollPeriod, Payslip
from notifications.utils import notify_payroll_generated, notify_payroll_released
from attendance.services import AttendanceProcessor
from settings.utils import get_setting

logger = logging.getLogger('fmh')


# ═══════════════════════════════════════════════════════════════════
#                       HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════

def safe_decimal(value, default=Decimal('0')):
    """Safely convert a value to Decimal, returning default on error."""
    if value is None or value == '':
        return default
    try:
        if isinstance(value, str):
            value = value.replace(',', '').strip()
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def safe_int(value, default=0):
    """Safely convert a value to int, returning default on error."""
    if value is None or value == '':
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def get_client_ip(request):
    """Get client IP address from request, handling proxy headers."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def validate_payslips_can_be_edited(period):
    """
    Check if payslips in a period can be edited.
    
    Returns:
        tuple: (can_edit, error_message)
    """
    if period.status not in [PayrollPeriod.Status.DRAFT, PayrollPeriod.Status.EDITED]:
        return (False, f"Payslips cannot be edited in {period.get_status_display()} state.")
    return (True, None)


def validate_payslips_can_be_generated(period):
    """
    Check if payslips in a period can be generated (locked for calculation).
    
    Returns:
        tuple: (can_generate, error_message)
    """
    if period.status == PayrollPeriod.Status.RELEASED:
        return (False, "This payroll period has already been released.")
    if period.payslips.count() == 0:
        return (False, "No payslips in this period to generate.")
    return (True, None)


def get_period_generation_restriction(periods, period_type, branch_id=None):
    """Return a user-facing error when a payroll type violates period rules."""
    completed_statuses = [PayrollPeriod.Status.GENERATED, PayrollPeriod.Status.RELEASED]

    relevant_periods = [
        period for period in periods
        if period.branch_id is None or period.branch_id == branch_id
    ] if branch_id is not None else list(periods)

    if branch_id is None and any(
        period.branch_id is not None and period.status in completed_statuses
        for period in relevant_periods
    ):
        return 'A payroll has already been generated for a specific branch this month. No All Branches payroll can be loaded or generated.'

    completed_periods = {
        period.period_type: period
        for period in relevant_periods
        if period.status in completed_statuses
    }

    if period_type in completed_periods:
        return 'This payroll period type has already been generated for the selected month and branch.'

    if period_type == PayrollPeriod.PeriodType.SEMI_SECOND and PayrollPeriod.PeriodType.SEMI_FIRST not in completed_periods:
        return 'Second-half payroll cannot be generated until the first-half payroll is generated for this month and branch.'

    return None


def get_payroll_report_rows(period):
    """Build the printable report rows and total net pay for a payroll period."""
    rows = []
    total_net_pay = Decimal('0')
    payslips = period.payslips.select_related('employee', 'employee__branch').order_by(
        'employee__last_name', 'employee__first_name'
    )

    for payslip in payslips:
        allowances = sum(
            (payslip.overtime_pay, payslip.holiday_pay, payslip.bonus,
             payslip.staff_allowance, payslip.thirteenth_month_pay),
            Decimal('0'),
        )
        net_pay = payslip.net_pay or Decimal('0')
        total_net_pay += net_pay
        rows.append({
            'employee': payslip.employee.full_name,
            'attendance': payslip.days_worked,
            'absences': payslip.days_absent,
            'base_salary': payslip.base_salary or Decimal('0'),
            'allowances': allowances,
            'deductions': payslip.total_deductions or Decimal('0'),
            'gross_pay': payslip.gross_pay or Decimal('0'),
            'net_pay': net_pay,
        })

    return rows, total_net_pay


# ═══════════════════════════════════════════════════════════════════
#                           DASHBOARD
# ═══════════════════════════════════════════════════════════════════

@login_required
@module_permission_required('payroll', 'MANAGE')
def payroll_dashboard(request):
    """Main payroll dashboard - simple overview with optimized queries."""
    today = date.today()

    # Current month period
    current_period = PayrollPeriod.objects.filter(
        month=today.month, year=today.year
    ).first()

    # Recent periods
    recent_periods = PayrollPeriod.objects.all()[:12]

    # Year-to-date stats - single optimized query
    ytd_stats = {'total_gross': 0, 'total_net': 0, 'count': 0}
    try:
        ytd_result = Payslip.objects.filter(
            payroll_period__year=today.year,
            status__in=['APPROVED', 'RELEASED']
        ).aggregate(
            total_gross=Sum('gross_pay'),
            total_net=Sum('net_pay'),
            count=Count('id')
        )
        ytd_stats = {
            'total_gross': ytd_result['total_gross'] or 0,
            'total_net': ytd_result['total_net'] or 0,
            'count': ytd_result['count'] or 0
        }
    except Exception as e:
        logger.warning(f"Error fetching YTD stats: {e}")

    # Active employees count
    active_employees = 0
    try:
        active_employees = StaffMember.objects.filter(
            is_active=True,
            user__isnull=False,
            user__assigned_role__is_staff_role=True
        ).exclude(user__assigned_role__code='superadmin').count()
    except Exception as e:
        logger.warning(f"Error counting active employees: {e}")

    # Pending payslips count
    pending_count = 0
    try:
        pending_count = Payslip.objects.filter(status='DRAFT').count()
    except Exception as e:
        logger.warning(f"Error counting pending payslips: {e}")

    # Last payroll cycle
    last_released = None
    try:
        last_released = PayrollPeriod.objects.filter(status='RELEASED').first()
    except Exception as e:
        logger.warning(f"Error fetching last released period: {e}")

    # Monthly trends - optimized single query for all 12 months
    monthly_trends = []
    try:
        # Generate month ranges
        trend_months = []
        for i in range(11, -1, -1):
            trend_date = today - timedelta(days=30*i)
            trend_months.append(
                (trend_date.month, trend_date.year, trend_date))

        # Single query for all relevant periods
        released_periods = {
            (p.month, p.year): p
            for p in PayrollPeriod.objects.filter(
                status='RELEASED',
                year__gte=today.year - 1
            )
        }

        for month, year, trend_date in trend_months:
            period = released_periods.get((month, year))
            amount = float(period.total_net or 0) if period else 0
            monthly_trends.append({
                'month': trend_date.strftime('%b'),
                'amount': amount,
                'full_month': trend_date.strftime('%B %Y')
            })
    except Exception as e:
        logger.warning(f"Error calculating monthly trends: {e}")
        # Fallback: empty trends
        for i in range(11, -1, -1):
            trend_date = today - timedelta(days=30*i)
            monthly_trends.append({
                'month': trend_date.strftime('%b'),
                'amount': 0,
                'full_month': trend_date.strftime('%B %Y')
            })

    # Recent activity - single optimized query
    recent_activity = []
    try:
        recent_activity = list(Payslip.objects.filter(
            payroll_period__year=today.year
        ).select_related(
            'employee', 'payroll_period'
        ).order_by('-payroll_period__generated_at')[:5])
    except Exception as e:
        logger.warning(f"Error fetching recent activity: {e}")

    # Upcoming payroll (next month)
    next_month = today.month + 1 if today.month < 12 else 1
    next_year = today.year if today.month < 12 else today.year + 1
    upcoming_period = None
    try:
        upcoming_period = PayrollPeriod.objects.filter(
            month=next_month, year=next_year
        ).first()
    except Exception as e:
        logger.warning(f"Error fetching upcoming period: {e}")

    # Total payroll this year - can reuse ytd_stats
    total_payroll_this_year = Decimal('0')
    try:
        result = Payslip.objects.filter(
            payroll_period__year=today.year,
            status='RELEASED'
        ).aggregate(Sum('net_pay'))['net_pay__sum']
        if result:
            total_payroll_this_year = result
    except Exception as e:
        logger.warning(f"Error calculating total payroll this year: {e}")

    context = {
        'current_period': current_period,
        'recent_periods': recent_periods,
        'ytd_stats': ytd_stats,
        'active_employees': active_employees,
        'pending_count': pending_count,
        'last_released': last_released,
        'upcoming_period': upcoming_period,
        'monthly_trends': json.dumps(monthly_trends),
        'recent_activity': recent_activity,
        'total_payroll_this_year': total_payroll_this_year,
        'current_month': today.month,
        'current_year': today.year,
        'tab': 'dashboard',
    }

    return render(request, 'payroll/dashboard.html', context)


# ═══════════════════════════════════════════════════════════════════
#                  LOAD PERIOD (Semi-Monthly Selection)
# ═══════════════════════════════════════════════════════════════════

@login_required
@module_permission_required('payroll', 'MANAGE')
def load_payroll_period(request):
    """
    NEW WORKFLOW: Load Period step.
    User selects payroll period (month/year), branch, and half-month period type.
    """
    return redirect('payroll:generate')


# ═══════════════════════════════════════════════════════════════════
#                      GENERATE PAYSLIPS
# ═══════════════════════════════════════════════════════════════════

@login_required
@module_permission_required('payroll', 'MANAGE')
def generate_payslips(request):
    """
    Render the existing payroll generation screen and load the selected period.
    """
    today = date.today()
    selected_month = safe_int(request.GET.get('month'), today.month)
    selected_year = safe_int(request.GET.get('year'), today.year)
    period_type = request.GET.get('period_type', PayrollPeriod.PeriodType.SEMI_FIRST)
    branch_value = request.GET.get('branch', '')
    selected_branch = None
    all_branches = branch_value.upper() == 'ALL'

    if branch_value.isdigit():
        selected_branch = Branch.objects.filter(pk=int(branch_value), is_active=True).first()

    if request.GET.get('load') == '1':
        if selected_month not in range(1, 13) or not 2020 <= selected_year <= 2100:
            messages.error(request, 'Invalid payroll period selected.')
            return redirect('payroll:generate')
        if period_type not in dict(PayrollPeriod.PeriodType.choices):
            messages.error(request, 'Invalid payroll period type selected.')
            return redirect('payroll:generate')
        if not selected_branch and not all_branches:
            messages.error(request, 'Select a branch or All Branches.')
            return redirect('payroll:generate')

        with transaction.atomic():
            sibling_periods = list(
                PayrollPeriod.objects.select_for_update().filter(
                    month=selected_month,
                    year=selected_year,
                )
            )
            restriction = get_period_generation_restriction(
                sibling_periods, period_type, selected_branch.id if selected_branch else None
            )
            if restriction:
                messages.error(request, restriction)
                return redirect('payroll:generate')

            period, _ = PayrollPeriod.objects.get_or_create(
                month=selected_month,
                year=selected_year,
                period_type=period_type,
                branch=selected_branch,
                defaults={'status': PayrollPeriod.Status.DRAFT},
            )
        return redirect('payroll:payslips', period_id=period.id)

    return render(request, 'payroll/generate.html', {
        'months': [{'num': i, 'name': date(2000, i, 1).strftime('%B')} for i in range(1, 13)],
        'years': range(today.year - 2, today.year + 6),
        'selected_month': selected_month,
        'selected_year': selected_year,
        'period_types': PayrollPeriod.PeriodType.choices,
        'selected_period_type': period_type,
        'branches': Branch.objects.filter(is_active=True).order_by('name'),
        'selected_branch': selected_branch,
        'all_branches': all_branches,
        'period_page': False,
        'employees': [],
    })


@login_required
@module_permission_required('payroll', 'MANAGE')
def generate_payslips_action(request, period_id=None):
    """
    CRITICAL: Generate/Lock payslips for a period with transaction.atomic() safety.
    
    This step locks all payslip edits and performs final calculations.
    Must be called AFTER all payslip edits are complete.
    """
    if request.method != 'POST':
        return redirect('payroll:payslips', period_id=period_id) if period_id else redirect('payroll:load_period')
    
    # Get period with defensive checks
    if not period_id:
        messages.error(request, 'No payroll period specified.')
        return redirect('payroll:load_period')
    
    period = get_object_or_404(PayrollPeriod, id=period_id)

    # CRITICAL: Use transaction.atomic() to prevent partial database writes
    try:
        with transaction.atomic():
            locked_periods = list(
                PayrollPeriod.objects.select_for_update().filter(
                    month=period.month,
                    year=period.year,
                ).filter(
                    Q(branch=period.branch)
                    | Q(branch__isnull=True)
                )
            )
            period = next(locked_period for locked_period in locked_periods if locked_period.id == period.id)
            restriction = get_period_generation_restriction(
                locked_periods, period.period_type, period.branch_id
            )
            if restriction:
                messages.error(request, restriction)
                return redirect('payroll:payslips', period_id=period.id)

            if period.branch_id is None and any(
                locked_period.id != period.id
                and locked_period.branch_id is not None
                and locked_period.status in [PayrollPeriod.Status.GENERATED, PayrollPeriod.Status.RELEASED]
                for locked_period in locked_periods
            ):
                messages.error(
                    request,
                    'A payroll has already been generated for a specific branch this month. '
                    'The All Branches payroll cannot be released.'
                )
                return redirect('payroll:payslips', period_id=period.id)

            if period.status not in [PayrollPeriod.Status.DRAFT, PayrollPeriod.Status.EDITED]:
                messages.error(
                    request,
                    f'Cannot generate payroll in {period.get_status_display()} state. '
                    f'Payroll must be in Draft or Edited state.'
                )
                return redirect('payroll:payslips', period_id=period.id)

            payslip_count = period.payslips.count()
            if payslip_count == 0:
                messages.error(request, 'No payslips in this period to generate.')
                return redirect('payroll:payslips', period_id=period.id)

            logger.info(f"Starting generation of payroll {period} with {payslip_count} payslips")
            
            # Lock all payslips and recalculate totals
            payslips = period.payslips.select_for_update().all()
            
            calculation_errors = []
            successful_count = 0
            
            for payslip in payslips:
                try:
                    # Recalculate totals based on current payslip state
                    payslip.calculate()
                    payslip.save(
                        update_fields=[
                            'gross_pay', 'total_allowances', 'total_deductions',
                            'total_clinic_contributions', 'net_pay'
                        ]
                    )
                    successful_count += 1
                except Exception as e:
                    calculation_errors.append(f"{payslip.employee.full_name}: {str(e)}")
                    logger.error(f"Error calculating payslip {payslip}: {e}")
            
            # If any errors occurred, raise to rollback the transaction
            if calculation_errors:
                error_msg = "Errors during payslip calculation: " + "; ".join(calculation_errors[:3])
                raise Exception(error_msg)
            
            # Update period totals and status
            period.status = PayrollPeriod.Status.GENERATED
            period.generated_at = timezone.now()
            period.save(update_fields=['status', 'generated_at'])
            
            # Recalculate period totals
            period.update_totals()
            
            logger.info(f"Successfully generated payroll {period}: {successful_count}/{payslip_count} payslips")
            
            # Log the generation
            from payroll.models import PayrollAuditLog
            PayrollAuditLog.log(
                user=request.user,
                action_type=PayrollAuditLog.ActionType.PERIOD_GENERATED,
                description=f"Generated payslips for {period.period_display} - {successful_count} payslips calculated and locked",
                payroll_period=period,
                metadata={
                    'payslip_count': payslip_count,
                    'period_type': period.period_type,
                    'success_count': successful_count,
                }
            )
            
            messages.success(
                request,
                f'✓ Payslips generated and locked! {successful_count} payslips calculated. '
                f'Proceed to Release Payroll when ready.'
            )
            
            # Notify relevant parties
            notify_payroll_generated(
                period,
                request.user,
                created_count=0,  # Not tracking new vs updated in new flow
                updated_count=payslip_count,
                total_employees=payslip_count,
            )
            
            return redirect('payroll:payslips', period_id=period.id)
    
    except Exception as e:
        logger.error(f"CRITICAL: Transaction rolled back during payroll generation for {period}: {e}")
        messages.error(
            request,
            f'Error generating payroll (transaction rolled back): {str(e)[:100]}'
        )
        return redirect('payroll:payslips', period_id=period.id)


@login_required
@module_permission_required('payroll', 'MANAGE')
def cancel_draft_period(request, period_id):
    """Discard an ungenerated payroll period created by the generation screen."""
    if request.method != 'POST':
        return redirect('payroll:payslips', period_id=period_id)

    period = get_object_or_404(PayrollPeriod, id=period_id)
    if period.status != PayrollPeriod.Status.DRAFT:
        messages.error(request, 'Only ungenerated draft payroll periods can be cancelled.')
    else:
        period_name = period.period_display
        period.delete()
        messages.success(request, f'{period_name} payroll draft was cancelled and removed.')
    return redirect('payroll:requests')


@login_required
@module_permission_required('payroll', 'MANAGE')
def discard_loaded_period(request, period_id):
    """Silently discard an ungenerated draft abandoned on the load screen."""
    if request.method != 'POST':
        return redirect('payroll:payslips', period_id=period_id)

    period = get_object_or_404(PayrollPeriod, id=period_id)
    if period.status == PayrollPeriod.Status.DRAFT and not period.generated_at:
        period.delete()
    return redirect('payroll:requests')


# ═══════════════════════════════════════════════════════════════════
#                      VIEW/LIST PAYSLIPS
# ═══════════════════════════════════════════════════════════════════

@login_required
@module_permission_required('payroll', 'MANAGE')
def payslips_list(request, period_id):
    """View all payslips for a period."""
    period = get_object_or_404(PayrollPeriod, id=period_id)
    branch_id = request.GET.get('branch', '').strip()
    selected_branch = Branch.objects.filter(pk=branch_id, is_active=True).first() if branch_id.isdigit() else None
    if period.status not in [PayrollPeriod.Status.DRAFT, PayrollPeriod.Status.EDITED]:
        selected_branch = period.branch
    elif not selected_branch and period.branch_id:
        selected_branch = period.branch

    if period.status == PayrollPeriod.Status.DRAFT:
        all_branches = branch_id.upper() == 'ALL' or (not branch_id and not period.branch_id)
        employee_queryset = StaffMember.objects.filter(
            is_active=True,
            user__isnull=False,
            user__assigned_role__is_staff_role=True,
        ).exclude(user__assigned_role__code='superadmin').order_by(
            '-user__assigned_role__hierarchy_level',
            'user__assigned_role__name',
            'last_name',
            'first_name',
        )
        if selected_branch:
            employee_queryset = employee_queryset.filter(branch=selected_branch)
        elif not all_branches:
            employee_queryset = StaffMember.objects.none()
        employees = list(employee_queryset.select_related('branch', 'user', 'user__assigned_role'))
        existing_payslip_records = []
        for employee in employees:
            payslip, was_created = Payslip.objects.get_or_create(
                payroll_period=period,
                employee=employee,
                defaults={'status': Payslip.Status.DRAFT},
            )
            if was_created:
                payslip.generate_from_employee()
                payslip.save()
                default_deductions = getattr(payslip, '_default_custom_deductions', [])
                for deduction in default_deductions:
                    payslip.custom_deductions.create(
                        reason=deduction['reason'],
                        amount=safe_decimal(deduction['amount']),
                    )
                if default_deductions:
                    payslip.calculate()
                    payslip.save(update_fields=[
                        'custom_deductions_total',
                        'total_deductions',
                        'net_pay',
                        'updated_at',
                    ])
            elif not payslip.custom_deductions.exists():
                default_deductions = getattr(employee, 'default_custom_deductions', None) or []
                for deduction in default_deductions:
                    reason = str(deduction.get('reason', '')).strip()
                    if reason:
                        payslip.custom_deductions.create(
                            reason=reason,
                            amount=safe_decimal(deduction.get('amount', 0)),
                        )
                if default_deductions:
                    payslip.calculate()
                    payslip.save(update_fields=[
                        'custom_deductions_total',
                        'total_deductions',
                        'net_pay',
                        'updated_at',
                    ])
            existing_payslip_records.append(payslip)

        from attendance.models import MonthlyAttendanceSummary
        attendance_count = MonthlyAttendanceSummary.objects.filter(
            staff_id__in=[employee.pk for employee in employees],
            period_start__year=period.year,
            period_start__month=period.month,
        ).count() if employees else 0
        return render(request, 'payroll/generate.html', {
            'period': period,
            'employees': employees,
            'existing_payslips': {payslip.employee_id: payslip.id for payslip in existing_payslip_records},
            'existing_payslip_records': existing_payslip_records,
            'months': [{'num': index, 'name': date(2000, index, 1).strftime('%B')} for index in range(1, 13)],
            'years': range(period.year - 2, period.year + 6),
            'selected_month': period.month,
            'selected_year': period.year,
            'period_types': PayrollPeriod.PeriodType.choices,
            'selected_period_type': period.period_type,
            'branches': Branch.objects.filter(is_active=True).order_by('name'),
            'selected_branch': selected_branch,
            'all_branches': all_branches,
            'employee_count': len(employees),
            'attendance_missing_count': len(employees) - attendance_count if employees else 0,
            'period_page': True,
        })

    # Get payslips safely, handling corrupted decimal data
    payslips = []
    try:
        # Get IDs first to avoid accessing decimal fields during query
        payslip_query = period.payslips.filter(employee__branch=selected_branch) if selected_branch else period.payslips.all()
        payslip_ids = list(payslip_query.values_list('id', flat=True))

        # Fetch each payslip individually with error handling
        for ps_id in payslip_ids:
            try:
                ps = Payslip.objects.select_related(
                    'employee', 'employee__branch').get(id=ps_id)
                payslips.append(ps)
            except Exception:
                # Skip payslips with corrupted data
                continue
    except Exception:
        # If we can't even get IDs, return empty list
        payslips = []

    context = {
        'period': period,
        'payslips': payslips,
        'can_edit_released': can_edit_released_payslip(request.user),
        'months': [{'num': index, 'name': date(2000, index, 1).strftime('%B')} for index in range(1, 13)],
        'years': range(period.year - 2, period.year + 6),
        'branches': Branch.objects.filter(is_active=True).order_by('name'),
        'selected_branch': selected_branch,
        'period_types': PayrollPeriod.PeriodType.choices,
        'selected_period_type': period.period_type,
        'all_branches': not period.branch_id,
    }

    return render(request, 'payroll/payslips_list.html', context)


def can_edit_released_payslip(user):
    """Check if user has permission to edit released payslips."""
    if not user or not user.is_authenticated:
        return False
    # Superadmin (hierarchy_level >= 10) can edit released payslips
    if hasattr(user, 'assigned_role') and user.assigned_role:
        return user.assigned_role.hierarchy_level >= 10
    return False


@login_required
@module_permission_required('payroll', 'MANAGE')
def period_report_view(request, period_id):
    """Render the printable payroll report for a generated period."""
    period = get_object_or_404(PayrollPeriod, id=period_id)
    rows, total_net_pay = get_payroll_report_rows(period)
    return render(request, 'payroll/period_report.html', {
        'period': period,
        'rows': rows,
        'employee_count': len(rows),
        'total_net_pay': total_net_pay,
    })


@login_required
@module_permission_required('payroll', 'MANAGE')
def payslip_edit(request, payslip_id):
    """Edit an individual payslip before its payroll period is generated."""
    payslip = get_object_or_404(
        Payslip.objects.select_related('employee', 'payroll_period').prefetch_related('custom_deductions'),
        id=payslip_id
    )

    if not payslip.custom_deductions.exists():
        default_deductions = getattr(payslip.employee, 'default_custom_deductions', None) or []
        for deduction in default_deductions:
            reason = str(deduction.get('reason', '')).strip()
            if reason:
                payslip.custom_deductions.create(
                    reason=reason,
                    amount=safe_decimal(deduction.get('amount', 0)),
                )
        if default_deductions:
            payslip.calculate()
            payslip.save(update_fields=[
                'custom_deductions_total',
                'total_deductions',
                'net_pay',
                'updated_at',
            ])

    period = payslip.payroll_period
    if period.status not in [PayrollPeriod.Status.DRAFT, PayrollPeriod.Status.EDITED]:
        messages.error(
            request, 'Payslips cannot be edited after payroll has been generated.')
        return redirect('payroll:payslips', period_id=period.id)

    from attendance.models import MonthlyAttendanceSummary
    from attendance.calculation_engine import WorkingDaysCalculator
    from attendance.models import DailyAttendance
    attendance_summary = MonthlyAttendanceSummary.objects.filter(
        staff=payslip.employee,
        period_start__year=period.year,
        period_start__month=period.month,
    ).first()

    # Refresh the displayed attendance from complete four-punch rows so an
    # older saved payslip cannot show the imported monthly total.
    period_start, period_end = period.get_period_start_end_dates()
    rest_days = int(get_setting('payroll_default_rest_days', 4))
    payslip.working_days = WorkingDaysCalculator.calculate_required_working_days(
        period.year,
        period.month,
        period.period_type,
        rest_days,
    )
    daily_records = DailyAttendance.objects.filter(
        staff=payslip.employee,
        attendance_date__range=[period_start, period_end],
    )
    has_detailed_punches = daily_records.filter(
        Q(morning_in__isnull=False)
        | Q(morning_out__isnull=False)
        | Q(afternoon_in__isnull=False)
        | Q(afternoon_out__isnull=False)
    ).exists()
    if has_detailed_punches:
        payslip.days_worked = daily_records.filter(
            morning_in__isnull=False,
            morning_out__isnull=False,
            afternoon_in__isnull=False,
            afternoon_out__isnull=False,
        ).count()
    else:
        payslip.days_worked = attendance_summary.attendance_days if attendance_summary else 0
    payslip.days_worked = min(payslip.days_worked, payslip.working_days)
    payslip.days_absent = max(0, payslip.working_days - payslip.days_worked)
    if payslip.base_salary > 0 and payslip.working_days > 0:
        payslip.daily_salary = payslip.base_salary / Decimal(str(payslip.working_days))

    if not attendance_summary:
        payslip.rest_days_mandatory = int(get_setting('payroll_default_rest_days', 4))
        payslip.working_days = WorkingDaysCalculator.calculate_required_working_days(
            period.year,
            period.month,
            period.period_type,
            payslip.rest_days_mandatory,
        )
        payslip.days_worked = 0
        payslip.days_absent = payslip.working_days
        payslip.rest_days_actual = 0
        payslip.absent_deduction = Decimal(str(get_setting('payroll_default_absent_deduction', 100)))
        payslip.paid_leave_days = Decimal('0')
        if payslip.base_salary > 0 and payslip.working_days > 0:
            payslip.daily_salary = payslip.base_salary / Decimal(str(payslip.working_days))
        else:
            payslip.daily_salary = Decimal('0')

    is_released = payslip.status == 'RELEASED'
    can_edit_released = can_edit_released_payslip(request.user)

    if request.method == 'POST':
        # Capture old values for audit log if editing released payslip
        old_values = None
        if is_released:
            old_values = {
                'gross_pay': str(payslip.gross_pay),
                'net_pay': str(payslip.net_pay),
                'total_deductions': str(payslip.total_deductions),
            }

        deduction_reasons = request.POST.getlist('deduction_reason[]') or request.POST.getlist('deduction_reason')
        deduction_amounts = request.POST.getlist('deduction_amount[]') or request.POST.getlist('deduction_amount')
        parsed_deductions = []
        deduction_errors = []

        for index, reason in enumerate(deduction_reasons):
            cleaned_reason = (reason or '').strip()
            raw_amount = deduction_amounts[index] if index < len(deduction_amounts) else ''
            cleaned_amount = safe_decimal(raw_amount)

            if not cleaned_reason and raw_amount:
                deduction_errors.append(f'Deduction row {index + 1} needs a reason/name.')
                continue
            if cleaned_reason and raw_amount in ('', None):
                deduction_errors.append(f'Deduction row {index + 1} needs an amount.')
                continue
            if cleaned_reason:
                parsed_deductions.append((cleaned_reason, cleaned_amount))

        if deduction_errors:
            messages.error(request, ' '.join(deduction_errors))
        else:
            with transaction.atomic():
                # Update allowances
                payslip.overtime_hours = safe_decimal(
                    request.POST.get('overtime_hours', 0))
                payslip.overtime_pay = safe_decimal(
                    request.POST.get('overtime_pay', 0))
                payslip.holiday_pay = safe_decimal(request.POST.get('holiday_pay', 0))
                payslip.bonus = safe_decimal(request.POST.get('bonus', 0))
                payslip.staff_allowance = safe_decimal(
                    request.POST.get(
                        'staff_allowance',
                        Decimal(str(get_setting('payroll_default_staff_allowance', 2000))) / Decimal('2')
                    ))

                # Update deductions
                payslip.sss = safe_decimal(request.POST.get('sss', 0))
                payslip.philhealth = safe_decimal(request.POST.get('philhealth', 0))
                payslip.pagibig = safe_decimal(request.POST.get('pagibig', 0))
                payslip.tax = Decimal('0')
                payslip.cash_advance = safe_decimal(
                    request.POST.get('cash_advance', 0))
                payslip.late_deduction = safe_decimal(
                    request.POST.get('late_deduction', 0))
                payslip.absent_deduction = safe_decimal(
                    request.POST.get('absent_deduction', 0))
                payslip.other_deductions = safe_decimal(
                    request.POST.get('other_deductions', 0))

                # Update attendance and payroll master values
                payslip.days_worked = safe_int(request.POST.get('days_worked', payslip.working_days), payslip.working_days)
                payslip.days_absent = safe_int(request.POST.get('days_absent', 0))
                payslip.working_days = safe_int(request.POST.get('working_days', payslip.working_days), payslip.working_days)
                payslip.rest_days_mandatory = safe_int(request.POST.get('rest_days_mandatory', payslip.rest_days_mandatory or 4), payslip.rest_days_mandatory or 4)
                if payslip.rest_days_mandatory <= 0:
                    payslip.rest_days_mandatory = 4
                payslip.paid_leave_type = request.POST.get('paid_leave_type', payslip.paid_leave_type or 'Sick Leave')
                payslip.paid_leave_days = safe_decimal(request.POST.get('paid_leave_days', 0))
                if payslip.paid_leave_days > Decimal(str(payslip.days_absent or 0)):
                    payslip.paid_leave_days = Decimal(str(payslip.days_absent or 0))
                
                # Update leave days (user manually categorizes from biometric absences)
                payslip.sick_leave_days = safe_decimal(request.POST.get('sick_leave_days', 0))
                payslip.regular_leave_days = safe_decimal(request.POST.get('regular_leave_days', 0))
                
                # Legacy fields (kept for compatibility)
                payslip.sick_hours = payslip.sick_leave_days * Decimal('8')  # Convert days to 8-hour days
                payslip.leave_hours = payslip.regular_leave_days * Decimal('8')  # Convert days to 8-hour days
                
                payslip.daily_salary = safe_decimal(request.POST.get('daily_salary', 0))

                # Recalculate daily salary based on current working days from attendance
                if payslip.working_days > 0 and payslip.base_salary > 0:
                    payslip.daily_salary = (
                        payslip.base_salary / Decimal(str(payslip.working_days))
                    )

                default_absent_deduction = Decimal(str(get_setting('payroll_default_absent_deduction', 100)))
                effective_absent_days = max(0, payslip.days_absent - int(payslip.paid_leave_days)) if payslip.paid_leave_days else payslip.days_absent
                payslip.absent_deduction = Decimal(str(effective_absent_days)) * default_absent_deduction
                
                # Calculate leave deduction based on manual categorization
                # Only regular (unpaid) leaves exceeding 4 rest days are deducted
                if payslip.rest_days_actual > payslip.rest_days_mandatory:
                    # User has excess absence days
                    # Only regular leave is deducted (sick leave is paid)
                    payslip.excess_leave_days = payslip.regular_leave_days
                    if payslip.regular_leave_days > 0 and payslip.daily_salary > 0:
                        payslip.rest_days_exceeded_deduction = payslip.regular_leave_days * payslip.daily_salary
                    else:
                        payslip.rest_days_exceeded_deduction = Decimal('0')
                else:
                    payslip.excess_leave_days = Decimal('0')
                    payslip.rest_days_exceeded_deduction = Decimal('0')

                # Notes
                payslip.notes = request.POST.get('notes', '')

                payslip.save()

                payslip.custom_deductions.all().delete()
                for reason, amount in parsed_deductions:
                    payslip.custom_deductions.create(reason=reason, amount=amount)

                # Recalculate and save after custom deductions are in place
                payslip.calculate()
                payslip.save()

                # Update period totals
                payslip.payroll_period.update_totals()
                
                # Mark period as EDITED (user has made modifications before generation)
                if payslip.payroll_period.status == PayrollPeriod.Status.DRAFT:
                    payslip.payroll_period.status = PayrollPeriod.Status.EDITED
                    payslip.payroll_period.edited_at = timezone.now()
                    payslip.payroll_period.save(update_fields=['status', 'edited_at'])
                    logger.info(f"Period {payslip.payroll_period} marked as EDITED")

                # Log the edit with enhanced metadata for released payslips
                from payroll.models import PayrollAuditLog

                metadata = {
                    'custom_deductions': [
                        {'reason': reason, 'amount': str(amount)}
                        for reason, amount in parsed_deductions
                    ]
                }
                if is_released and old_values:
                    metadata.update({
                        'edited_after_release': True,
                        'old_values': old_values,
                        'new_values': {
                            'gross_pay': str(payslip.gross_pay),
                            'net_pay': str(payslip.net_pay),
                            'total_deductions': str(payslip.total_deductions),
                        }
                    })

                action_desc = f"Edited payslip for {payslip.employee.full_name} ({payslip.payroll_period.period_display})"
                if is_released:
                    action_desc = f"[RELEASED EDIT] {action_desc}"

                PayrollAuditLog.log(
                    user=request.user,
                    action_type=PayrollAuditLog.ActionType.PAYSLIP_EDITED,
                    description=action_desc,
                    payslip=payslip,
                    payroll_period=payslip.payroll_period,
                    staff_member=payslip.employee,
                    metadata=metadata,
                    ip_address=get_client_ip(request)
                )

                messages.success(
                    request, f'Payslip for {payslip.employee.full_name} updated.')
                return redirect('payroll:payslips', period_id=payslip.payroll_period.id)

    configured_paid_leave_types = get_setting('payroll_paid_leave_types', ['Sick Leave', 'Emergency Leave'])
    if isinstance(configured_paid_leave_types, str):
        configured_paid_leave_types = [
            item.strip() for item in configured_paid_leave_types.splitlines() if item.strip()
        ]
    if not configured_paid_leave_types:
        configured_paid_leave_types = ['Sick Leave', 'Emergency Leave']

    configured_staff_allowance = (
        Decimal(str(get_setting('payroll_default_staff_allowance', 2000))) / Decimal('2')
    )
    display_rest_days = payslip.rest_days_mandatory
    if period.period_type in [
        PayrollPeriod.PeriodType.SEMI_FIRST,
        PayrollPeriod.PeriodType.SEMI_SECOND,
    ]:
        display_rest_days = max(1, display_rest_days // 2)

    # Refresh automatic statutory values for the editable preview without saving.
    payslip.calculate()

    context = {
        'payslip': payslip,
        'period': payslip.payroll_period,
        'is_released': is_released,
        'can_edit_released': can_edit_released,
        'custom_deductions': list(payslip.custom_deductions.all()),
        'show_sss': get_setting('payroll_auto_statutory', True) and get_setting('payroll_enable_sss', True),
        'show_philhealth': get_setting('payroll_auto_statutory', True) and get_setting('payroll_enable_philhealth', True),
        'show_pagibig': get_setting('payroll_auto_statutory', True) and get_setting('payroll_enable_pagibig', True),
        'default_staff_allowance': configured_staff_allowance,
        'default_overtime_pay_per_hour': get_setting('payroll_default_overtime_pay_per_hour', 120),
        'default_absent_deduction': get_setting('payroll_default_absent_deduction', 100),
        'paid_leave_options': configured_paid_leave_types,
        'daily_salary_display': payslip.daily_salary,
        'display_rest_days': display_rest_days,
        'staff_allowance_display': configured_staff_allowance,
    }

    return render(request, 'payroll/payslip_edit.html', context)


@login_required
@module_permission_required('payroll', 'MANAGE')
def payslip_delete(request, payslip_id):
    """Delete individual payslip. Released payslips require elevated permissions."""
    if request.method != 'POST':
        return redirect('payroll:payslips', period_id=get_object_or_404(Payslip, id=payslip_id).payroll_period_id)
    payslip = get_object_or_404(
        Payslip.objects.select_related('employee', 'payroll_period'),
        id=payslip_id
    )
    period = payslip.payroll_period

    if period.status not in [PayrollPeriod.Status.DRAFT, PayrollPeriod.Status.EDITED]:
        messages.error(
            request, 'Payslips can only be deleted before payroll is generated.')
        return redirect('payroll:payslips', period_id=period.id)

    is_released = payslip.status == 'RELEASED'
    can_delete = can_edit_released_payslip(request.user)

    # Only allow deletion of released payslips if user has elevated permissions
    if is_released and not can_delete:
        messages.error(
            request, 'You do not have permission to delete released payslips. Contact a Superadmin.')
        return redirect('payroll:payslips', period_id=payslip.payroll_period.id)

    if request.method == 'POST':
        employee_name = payslip.employee.full_name
        period_display = period.period_display

        # Capture info for audit log before deletion
        deleted_metadata = {
            'deleted_after_release': is_released,
            'deleted_payslip': {
                'employee_name': employee_name,
                'base_salary': str(payslip.base_salary),
                'gross_pay': str(payslip.gross_pay),
                'net_pay': str(payslip.net_pay),
                'total_deductions': str(payslip.total_deductions),
            }
        }

        # Log the deletion before removing the payslip
        from payroll.models import PayrollAuditLog
        PayrollAuditLog.log(
            user=request.user,
            action_type=PayrollAuditLog.ActionType.PAYSLIP_DELETED,
            description=f"[DELETED{'- RELEASED' if is_released else ''}] Payslip for {employee_name} ({period_display})",
            payslip=None,  # Will be None since we're deleting it
            payroll_period=period,
            staff_member=payslip.employee,
            metadata=deleted_metadata,
            ip_address=get_client_ip(request)
        )

        # Delete the payslip
        payslip.delete()

        # Update period totals
        period.update_totals()

        messages.success(
            request, f'Payslip for {employee_name} has been deleted.')
        return redirect('payroll:payslips', period_id=period.id)


# ═══════════════════════════════════════════════════════════════════
#                      RELEASE PAYROLL
# ═══════════════════════════════════════════════════════════════════

@login_required
@module_permission_required('payroll', 'MANAGE')
def release_payroll(request, period_id):
    """
    Release payroll - mark all payslips as released and send emails to staff.
    
    CRITICAL: Period must be in GENERATED state (payslips calculated and locked).
    This prevents releasing payroll that hasn't been finalized.
    """
    period = get_object_or_404(PayrollPeriod, id=period_id)

    # Validate period state - must be GENERATED
    if period.status != PayrollPeriod.Status.GENERATED:
        if period.status == PayrollPeriod.Status.RELEASED:
            messages.warning(request, 'This payroll has already been released.')
        elif period.status in [PayrollPeriod.Status.DRAFT, PayrollPeriod.Status.EDITED]:
            messages.error(
                request,
                f'Cannot release payroll in {period.get_status_display()} state. '
                f'Please generate payroll first (lock calculations) before releasing.'
            )
        else:
            messages.error(request, f'Cannot release payroll in {period.get_status_display()} state.')
        return redirect('payroll:payslips', period_id=period.id)

    from payroll.models import PayrollAuditLog
    from payroll.email_service import send_payslip_email
    
    # Use transaction.atomic() for release operation
    try:
        with transaction.atomic():
            now = timezone.now()

            locked_periods = list(
                PayrollPeriod.objects.select_for_update().filter(
                    month=period.month,
                    year=period.year,
                )
            )
            if period.branch_id is None and any(
                locked_period.id != period.id
                and locked_period.branch_id is not None
                and locked_period.status in [PayrollPeriod.Status.GENERATED, PayrollPeriod.Status.RELEASED]
                for locked_period in locked_periods
            ):
                messages.error(
                    request,
                    'A payroll has already been generated for a specific branch this month. '
                    'The All Branches payroll cannot be released.'
                )
                return redirect('payroll:payslips', period_id=period.id)

            # Get payslip count before release
            payslip_count = period.payslips.count()
            if payslip_count == 0:
                messages.error(request, 'No payslips in this period to release.')
                return redirect('payroll:payslips', period_id=period.id)

            # Mark all payslips as released (use select_for_update for locking)
            payslips_to_release = period.payslips.select_for_update().all()
            payslips_to_release.update(
                status='RELEASED',
                released_at=now
            )

            # Update period status
            period.status = 'RELEASED'
            period.released_at = now
            period.released_by = request.user
            period.save(update_fields=['status', 'released_at', 'released_by'])

            logger.info(f"Released payroll {period}: {payslip_count} payslips marked as RELEASED")

            # Send emails to all employees with email addresses
            sent_count = 0
            failed_count = 0

            payslip_ids = []
            try:
                payslip_ids = list(period.payslips.filter(
                    employee__email__isnull=False
                ).exclude(employee__email='').values_list('id', flat=True))
            except Exception as e:
                logger.warning(f"Error fetching payslip IDs for email: {e}")
                payslip_ids = []

            for ps_id in payslip_ids:
                try:
                    payslip = Payslip.objects.select_related(
                        'employee').get(id=ps_id)
                    try:
                        sent, reason = send_payslip_email(payslip)
                        if sent:
                            sent_count += 1
                        else:
                            failed_count += 1
                            logger.warning(
                                'Failed to send email for payslip %s: %s',
                                payslip,
                                reason,
                            )
                    except Exception as e:
                        failed_count += 1
                        logger.warning('Failed to send email for payslip %s: %s', payslip, e)
                    continue
                except Exception as e:
                    failed_count += 1
                    logger.error('Error processing payslip %s for email: %s', ps_id, e)
                    continue

            # Log the release with comprehensive audit trail
            total_net_value = Decimal('0')
            try:
                if period.total_net:
                    total_net_value = period.total_net
            except Exception:
                total_net_value = Decimal('0')

            PayrollAuditLog.log(
                user=request.user,
                action_type=PayrollAuditLog.ActionType.PERIOD_RELEASED,
                description=f"Released payroll for {period.period_display} - {payslip_count} payslips, {sent_count} emails sent",
                payroll_period=period,
                metadata={
                    'employee_count': payslip_count,
                    'total_net': str(total_net_value),
                    'emails_sent': sent_count,
                    'emails_failed': failed_count
                }
            )

            # Display success message with details
            if sent_count > 0:
                messages.success(
                    request,
                    f'✓ Payroll released! {payslip_count} payslips sent to {sent_count} employee email(s).'
                )
            else:
                messages.success(
                    request,
                    f'✓ Payroll released! {payslip_count} payslips marked as released.'
                )

            if failed_count > 0:
                messages.warning(
                    request,
                    f'⚠ {failed_count} email(s) failed. Check email logs for details.'
                )

            notify_payroll_released(
                period,
                request.user,
                payslip_count=payslip_count,
                emails_sent=sent_count,
            )

            return redirect('payroll:payslips', period_id=period.id)
    
    except Exception as e:
        logger.error(f"CRITICAL: Error releasing payroll {period}: {e}")
        messages.error(
            request,
            f'Error releasing payroll (transaction rolled back): {str(e)[:100]}'
        )
        return redirect('payroll:payslips', period_id=period.id)


# ═══════════════════════════════════════════════════════════════════
#                      PRINT PAYSLIP
# ═══════════════════════════════════════════════════════════════════

@login_required
@module_permission_required('payroll', 'MANAGE')
def payslip_print(request, payslip_id):
    """Print-friendly payslip view."""
    payslip = get_object_or_404(
        Payslip.objects.select_related(
            'employee', 'employee__branch', 'payroll_period').prefetch_related('custom_deductions'),
        id=payslip_id
    )

    # Determine a sensible return URL: prefer explicit `return_to` GET param,
    # then the HTTP_REFERER header, then fall back to the payslips list for
    # the payslip's payroll period.
    from django.urls import reverse

    explicit_return = request.GET.get('return_to')
    referer = request.META.get('HTTP_REFERER')
    fallback = reverse('payroll:payslips', args=[payslip.payroll_period.id])

    return_to = explicit_return or referer or fallback

    context = {
        'payslip': payslip,
        'print_mode': True,
        'return_to': return_to,
        'payroll_signatory': get_setting('payroll_signatory_name_title', 'Authorized by Finance / Human Resources'),
    }

    return render(request, 'payroll/payslip_print.html', context)


# ═══════════════════════════════════════════════════════════════════
#                      QUICK ACTIONS / API
# ═══════════════════════════════════════════════════════════════════

@login_required
@module_permission_required('payroll', 'MANAGE')
def payslip_approve(request, payslip_id):
    """Approve a single payslip."""
    payslip = get_object_or_404(Payslip, id=payslip_id)

    if payslip.status == 'DRAFT':
        payslip.status = 'APPROVED'
        payslip.save()
        messages.success(
            request, f'Payslip for {payslip.employee.full_name} approved.')

    return redirect('payroll:payslips', period_id=payslip.payroll_period.id)


@login_required
@module_permission_required('payroll', 'MANAGE')
def approve_all_payslips(request, period_id):
    """Approve all payslips in a period."""
    period = get_object_or_404(PayrollPeriod, id=period_id)

    count = period.payslips.filter(status='DRAFT').update(status='APPROVED')
    messages.success(request, f'{count} payslips approved.')

    return redirect('payroll:payslips', period_id=period.id)


@login_required
@module_permission_required('payroll', 'MANAGE')
def delete_period(request, period_id):
    """Delete a payroll period. Released periods require elevated permissions."""
    if request.method != 'POST':
        return redirect('payroll:requests')
    period = get_object_or_404(PayrollPeriod, id=period_id)

    is_released = period.status == 'RELEASED'
    can_delete = can_edit_released_payslip(request.user)

    # Released periods require elevated permissions
    if is_released and not can_delete:
        messages.error(
            request, 'You do not have permission to delete released payroll periods. Contact a Superadmin.')
        return redirect('payroll:requests')

    if request.method == 'POST':
        period_name = period.period_display
        payslip_count = period.payslips.count()
        total_net = period.total_net or 0

        # Log before deletion
        from payroll.models import PayrollAuditLog
        PayrollAuditLog.log(
            user=request.user,
            action_type=PayrollAuditLog.ActionType.PERIOD_DELETED,
            description=f"[DELETED{'- RELEASED' if is_released else ''}] Period {period_name} with {payslip_count} payslips",
            payroll_period=None,
            metadata={
                'deleted_after_release': is_released,
                'period_name': period_name,
                'payslip_count': payslip_count,
                'total_net_pay': str(total_net),
            },
            ip_address=get_client_ip(request)
        )

        period.delete()
        messages.success(
            request, f'Payroll period "{period_name}" and all {payslip_count} payslips deleted.')
        return redirect('payroll:requests')


# ═══════════════════════════════════════════════════════════════════
#                    TAB VIEWS - VETS (EMPLOYEES)
# ═══════════════════════════════════════════════════════════════════

@login_required
@module_permission_required('payroll', 'MANAGE')
def payroll_vets(request):
    """View all employees with their payroll information."""
    today = date.today()

    # Get all branches for filter dropdown
    from branches.models import Branch
    branches = Branch.objects.all().order_by('name')

    # Current period payslips
    current_period = PayrollPeriod.objects.filter(
        month=today.month, year=today.year
    ).first()

    # Get employees safely with error handling
    employee_data = []
    active_count = 0
    branch_filter = request.GET.get('branch')

    try:
        # Get all active employee IDs first - use values to avoid decimal fields
        if branch_filter:
            emp_ids = list(StaffMember.objects.filter(
                is_active=True,
                user__isnull=False,
                user__assigned_role__is_staff_role=True,
                branch_id=branch_filter
            ).exclude(user__assigned_role__code='superadmin').order_by(
                '-user__assigned_role__hierarchy_level',
                'user__assigned_role__name',
                'last_name',
                'first_name',
            ).values_list('id', flat=True))
        else:
            emp_ids = list(StaffMember.objects.filter(
                is_active=True,
                user__isnull=False,
                user__assigned_role__is_staff_role=True
            ).exclude(user__assigned_role__code='superadmin').order_by(
                '-user__assigned_role__hierarchy_level',
                'user__assigned_role__name',
                'last_name',
                'first_name',
            ).values_list('id', flat=True))

        # Try to get active count - might fail if corrupted data exists
        try:
            all_active = StaffMember.objects.filter(
                is_active=True,
                user__isnull=False,
                user__assigned_role__is_staff_role=True
            ).exclude(user__assigned_role__code='superadmin').order_by(
                '-user__assigned_role__hierarchy_level',
                'user__assigned_role__name',
                'last_name',
                'first_name',
            ).values_list('id')
            active_count = len(list(all_active))
        except Exception:
            active_count = 0

        # Build employee payroll data - handle corrupted data
        for emp_id in emp_ids:
            try:
                emp = StaffMember.objects.get(id=emp_id)

                # Current period payslip
                current_payslip = None
                if current_period:
                    current_payslip = Payslip.objects.filter(
                        employee=emp,
                        payroll_period=current_period
                    ).first()

                # Last released payslip
                last_payslip = Payslip.objects.filter(
                    employee=emp,
                    status='RELEASED'
                ).order_by('-payroll_period__released_at').first()

                # YTD total
                ytd_gross = Decimal('0')
                try:
                    ytd_result = Payslip.objects.filter(
                        employee=emp,
                        payroll_period__year=today.year,
                        status='RELEASED'
                    ).aggregate(Sum('gross_pay'))['gross_pay__sum']
                    if ytd_result:
                        ytd_gross = ytd_result
                except Exception:
                    ytd_gross = Decimal('0')

                employee_data.append({
                    'employee': emp,
                    'current_payslip': current_payslip,
                    'last_payslip': last_payslip,
                    'ytd_gross': ytd_gross,
                })
            except Exception:
                # Skip this employee if there's any error accessing their data
                continue

    except Exception:
        # If we can't even get the employee IDs, return empty list
        employee_data = []

    context = {
        'tab': 'vets',
        'employees': employee_data,
        'active_count': active_count,
        'filtered_count': len(employee_data),
        'branches': branches,
        'selected_branch': request.GET.get('branch'),
        'current_period': current_period,
    }

    return render(request, 'payroll/vets.html', context)


# ═══════════════════════════════════════════════════════════════════
#                 TAB VIEWS - SEND PAYSLIPS
# ═══════════════════════════════════════════════════════════════════

@login_required
@module_permission_required('payroll', 'MANAGE')
def payroll_requests(request):
    """View payroll generation and payslip delivery history."""
    date.today()

    # Get all payroll periods - with error handling
    periods_by_year = {}
    total_periods = 0
    released_count = 0
    draft_count = 0
    generated_count = 0

    try:
        all_periods = list(PayrollPeriod.objects.exclude(
            status=PayrollPeriod.Status.DRAFT
        ).values_list('id', 'year', 'month', 'status'))
        total_periods = len(all_periods)

        # Count by status
        released_count = sum(1 for p in all_periods if p[3] == 'RELEASED')
        draft_count = sum(1 for p in all_periods if p[3] == 'DRAFT')
        generated_count = sum(1 for p in all_periods if p[3] == 'GENERATED')

        # Now fetch full period objects for display
        for period_id in [p[0] for p in all_periods]:
            try:
                period = PayrollPeriod.objects.get(id=period_id)
                year = period.year
                if year not in periods_by_year:
                    periods_by_year[year] = []
                periods_by_year[year].append(period)
            except Exception:
                continue
    except Exception:
        periods_by_year = {}
        total_periods = 0
        released_count = 0
        draft_count = 0
        generated_count = 0

    context = {
        'tab': 'requests',
        'periods_by_year': periods_by_year,
        'total_periods': total_periods,
        'released_count': released_count,
        'draft_count': draft_count,
        'generated_count': generated_count,
        'can_delete_released': can_edit_released_payslip(request.user),
    }

    return render(request, 'payroll/requests.html', context)


# ═══════════════════════════════════════════════════════════════════
#                    VET DETAILS EDITOR
# ═══════════════════════════════════════════════════════════════════

@login_required
@module_permission_required('payroll', 'MANAGE')
def vet_detail(request, staff_id):
    """
    Specialized Vet Details editor for payroll-specific data.
    Manage base salary, performance bonuses, and deductions.
    """
    staff = get_object_or_404(StaffMember, id=staff_id, is_active=True)
    today = date.today()
    payroll_default_staff_allowance = get_setting('payroll_default_staff_allowance', 2000)

    # Import here to avoid circular import
    from payroll.models import PayrollAuditLog

    if request.method == 'POST':
        old_salary = staff.salary
        old_staff_allowance = getattr(
            staff, 'default_staff_allowance', Decimal('2000'))
        old_days_worked = getattr(staff, 'default_days_worked', 22)
        old_custom_deductions = list(getattr(staff, 'default_custom_deductions', []) or [])

        # Update salary and allowances
        new_salary = safe_decimal(request.POST.get('base_salary', 0))
        new_staff_allowance = safe_decimal(
            request.POST.get('default_staff_allowance', 2000))
        new_days_worked = safe_int(
            request.POST.get('default_days_worked', 22), 22)

        deduction_reasons = request.POST.getlist('deduction_reason[]') or request.POST.getlist('deduction_reason')
        deduction_amounts = request.POST.getlist('deduction_amount[]') or request.POST.getlist('deduction_amount')
        new_custom_deductions = []
        deduction_errors = []

        for index, reason in enumerate(deduction_reasons):
            cleaned_reason = (reason or '').strip()
            raw_amount = deduction_amounts[index] if index < len(deduction_amounts) else ''
            cleaned_amount = safe_decimal(raw_amount)

            if not cleaned_reason and raw_amount:
                deduction_errors.append(f'Deduction row {index + 1} needs a reason/name.')
                continue
            if cleaned_reason and raw_amount in ('', None):
                deduction_errors.append(f'Deduction row {index + 1} needs an amount.')
                continue
            if cleaned_reason:
                new_custom_deductions.append({
                    'reason': cleaned_reason,
                    'amount': str(cleaned_amount),
                })

        if deduction_errors:
            messages.error(request, ' '.join(deduction_errors))
            return redirect('payroll:vet_detail', staff_id=staff.id)

        staff.salary = new_salary
        staff.default_staff_allowance = new_staff_allowance
        staff.default_days_worked = new_days_worked
        staff.default_custom_deductions = new_custom_deductions
        staff.save()

        # Log the change if anything changed
        changes = []
        if old_salary != new_salary:
            changes.append(f"salary ₱{old_salary:,.2f} → ₱{new_salary:,.2f}")
        if old_staff_allowance != new_staff_allowance:
            changes.append(
                f"staff allowance ₱{old_staff_allowance:,.2f} → ₱{new_staff_allowance:,.2f}")
        if old_days_worked != new_days_worked:
            changes.append(
                f"default days {old_days_worked} → {new_days_worked}")
        if old_custom_deductions != new_custom_deductions:
            changes.append('custom deductions updated')

        if changes:
            PayrollAuditLog.log(
                user=request.user,
                action_type=PayrollAuditLog.ActionType.VET_SALARY_UPDATED,
                description=f"Updated payroll config for {staff.full_name}: {', '.join(changes)}",
                staff_member=staff,
                metadata={
                    'old_salary': str(old_salary),
                    'new_salary': str(new_salary),
                    'old_staff_allowance': str(old_staff_allowance),
                    'new_staff_allowance': str(new_staff_allowance),
                    'old_days_worked': old_days_worked,
                    'new_days_worked': new_days_worked,
                    'old_custom_deductions': old_custom_deductions,
                    'new_custom_deductions': new_custom_deductions,
                },
                ip_address=get_client_ip(request)
            )

        messages.success(
            request, f'Payroll data for {staff.full_name} updated successfully.')
        return redirect('payroll:vet_detail', staff_id=staff.id)

    # Get payroll history for this employee - with error handling
    payslip_history = []
    try:
        ps_ids = list(Payslip.objects.filter(
            employee=staff
        ).values_list('id', flat=True).order_by('-payroll_period__year', '-payroll_period__month')[:12])

        for ps_id in ps_ids:
            try:
                ps = Payslip.objects.select_related(
                    'payroll_period').get(id=ps_id)
                payslip_history.append(ps)
            except Exception:
                continue
    except Exception:
        payslip_history = []

    # Calculate YTD stats - with error handling
    ytd_stats = {
        'total_gross': Decimal('0'),
        'total_net': Decimal('0'),
        'total_deductions': Decimal('0'),
        'count': 0
    }
    try:
        stats = Payslip.objects.filter(
            employee=staff,
            payroll_period__year=today.year,
            status='RELEASED'
        ).aggregate(
            total_gross=Sum('gross_pay'),
            total_net=Sum('net_pay'),
            total_deductions=Sum('total_deductions'),
            count=Count('id')
        )
        if stats and stats['total_gross'] is not None:
            ytd_stats = stats
    except Exception:
        # Keep default values on error
        pass

    # Get recent audit logs for this staff - with error handling
    recent_logs = []
    try:
        log_ids = list(PayrollAuditLog.objects.filter(
            staff_member=staff
        ).values_list('id', flat=True).order_by('-created_at')[:10])

        for log_id in log_ids:
            try:
                log = PayrollAuditLog.objects.get(id=log_id)
                recent_logs.append(log)
            except Exception:
                continue
    except Exception:
        recent_logs = []

    context = {
        'tab': 'vets',
        'staff': staff,
        'payslip_history': payslip_history,
        'ytd_stats': ytd_stats,
        'recent_logs': recent_logs,
        'staff_allowance_display': staff.default_staff_allowance or payroll_default_staff_allowance,
        'payroll_default_staff_allowance': payroll_default_staff_allowance,
    }

    return render(request, 'payroll/vet_detail.html', context)


# ═══════════════════════════════════════════════════════════════════
#                    COMPREHENSIVE AUDIT LOG VIEW
# ═══════════════════════════════════════════════════════════════════

@login_required
@module_permission_required('payroll', 'MANAGE')
def audit_log_view(request):
    """
    Comprehensive audit log view showing all system actions.
    Filterable by action type and date range.
    Only superadmin can view audit logs.
    """
    from django.core.paginator import Paginator
    from payroll.models import PayrollAuditLog
    from datetime import datetime

    # Build base queryset with relationships pre-fetched
    base_logs = PayrollAuditLog.objects.select_related(
        'user', 'payroll_period', 'payslip', 'staff_member'
    ).order_by('-created_at')

    # Apply action type filter
    action_filter = request.GET.get('action_type', '').strip()
    if action_filter:
        base_logs = base_logs.filter(action_type=action_filter)

    # Apply date range filters with validation
    date_from = request.GET.get('date_from', '').strip()
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            base_logs = base_logs.filter(created_at__date__gte=from_date)
        except (ValueError, TypeError):
            # Invalid date format, skip this filter
            pass

    date_to = request.GET.get('date_to', '').strip()
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
            base_logs = base_logs.filter(created_at__date__lte=to_date)
        except (ValueError, TypeError):
            # Invalid date format, skip this filter
            pass

    # Calculate stats based on FILTERED logs (not all logs)
    stats = {
        'total': 0,
        'created': 0,
        'edited': 0,
        'released': 0,
    }

    try:
        # Stats reflect current filters
        stats['total'] = base_logs.count()
        stats['created'] = base_logs.filter(
            action_type__in=['PERIOD_GENERATED', 'PAYSLIP_CREATED']).count()
        stats['edited'] = base_logs.filter(
            action_type__in=['PAYSLIP_EDITED', 'VET_SALARY_UPDATED']).count()
        stats['released'] = base_logs.filter(
            action_type__in=['PERIOD_RELEASED', 'PAYSLIP_SENT']).count()
    except Exception:
        stats = {'total': 0, 'created': 0, 'edited': 0, 'released': 0}

    # Pagination
    paginator = Paginator(base_logs, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Get only action types that actually exist in the database or are still mapped to logs.
    existing_action_types = set(base_logs.values_list('action_type', flat=True).distinct())
    action_type_choices = [
        (value, label)
        for value, label in PayrollAuditLog.ActionType.choices
        if value in existing_action_types
    ]

    context = {
        'tab': 'logs',
        'logs': page_obj,
        'stats': stats,
        'action_type_choices': action_type_choices,
    }

    return render(request, 'payroll/audit_log.html', context)


@login_required
@module_permission_required('payroll', 'MANAGE')
def audit_log_detail(request, log_id):
    """Display detailed information about a specific audit log entry."""
    from payroll.models import PayrollAuditLog

    try:
        log = PayrollAuditLog.objects.select_related(
            'user', 'payroll_period', 'payslip', 'staff_member', 'payslip__employee'
        ).get(id=log_id)
    except PayrollAuditLog.DoesNotExist:
        from django.http import Http404
        raise Http404("Audit log not found")
    except Exception:
        from django.http import Http404
        raise Http404("Error loading audit log")

    context = {
        'tab': 'logs',
        'log': log,
    }

    return render(request, 'payroll/audit_log_detail.html', context)


def get_payroll_report_rows(period):
    """Return report rows and the period net total from related payslips."""
    payslips = period.payslips.select_related('employee').order_by(
        'employee__last_name', 'employee__first_name'
    )
    rows = [
        {
            'employee': payslip.employee.full_name,
            'position': payslip.employee.get_position_display(),
            'days_worked': payslip.days_worked,
            'days_absent': payslip.days_absent,
            'allowances': sum(
                (
                    payslip.overtime_pay,
                    payslip.holiday_pay,
                    payslip.bonus,
                    payslip.staff_allowance,
                    payslip.thirteenth_month_pay,
                ),
                Decimal('0'),
            ),
            'gross_pay': payslip.gross_pay,
            'total_deductions': payslip.total_deductions,
            'net_pay': payslip.net_pay,
        }
        for payslip in payslips
    ]
    return rows, sum((row['net_pay'] for row in rows), Decimal('0'))


@login_required
@module_permission_required('payroll', 'MANAGE')
def period_report_view(request, period_id):
    """Render an ORM-backed summary report for one payroll period."""
    period = get_object_or_404(PayrollPeriod, id=period_id)
    rows, total_net_pay = get_payroll_report_rows(period)
    return render(request, 'payroll/period_report.html', {
        'period': period,
        'rows': rows,
        'employee_count': len(rows),
        'total_gross_pay': period.total_gross,
        'total_deductions': period.total_deductions,
        'total_net_pay': total_net_pay,
    })


# ═══════════════════════════════════════════════════════════════════
#                    HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════

def get_client_ip(request):
    """Extract client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


# ═══════════════════════════════════════════════════════════════════
#               EXPORT FEATURES - CSV & EXCEL
# ═══════════════════════════════════════════════════════════════════

@login_required
@module_permission_required('payroll', 'MANAGE')
def export_payslips_csv(request, period_id):
    """Export payslips to CSV format."""
    import csv
    from django.http import HttpResponse

    period = get_object_or_404(PayrollPeriod, id=period_id)

    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="payslips_{period.period_display}.csv"'

    writer = csv.writer(response)

    # Write header
    writer.writerow([
        'Employee Name', 'Position', 'Branch', 'Base Salary',
        'Overtime Pay', 'Holiday Pay', 'Bonus', 'Staff Allowance',
        'Gross Pay', 'SSS', 'PhilHealth', 'PAG-IBIG', 'Tax',
        'Cash Advance', 'Other Deductions', 'Net Pay', 'Status'
    ])

    # Get payslips safely - ID first approach
    payslips = []
    try:
        payslip_ids = list(period.payslips.values_list('id', flat=True))
        for ps_id in payslip_ids:
            try:
                ps = Payslip.objects.select_related(
                    'employee', 'employee__branch').get(id=ps_id)
                payslips.append(ps)
            except Exception:
                continue
    except Exception:
        payslips = []

    # Write data rows with error handling for decimal fields
    totals_gross = Decimal('0')
    totals_net = Decimal('0')

    for payslip in payslips:
        try:
            # Get decimal values with defaults
            base_salary = payslip.base_salary or Decimal('0')
            overtime_pay = payslip.overtime_pay or Decimal('0')
            holiday_pay = payslip.holiday_pay or Decimal('0')
            bonus = payslip.bonus or Decimal('0')
            staff_allowance = payslip.staff_allowance or Decimal('0')
            gross_pay = payslip.gross_pay or Decimal('0')
            sss = payslip.sss or Decimal('0')
            philhealth = payslip.philhealth or Decimal('0')
            pagibig = payslip.pagibig or Decimal('0')
            tax = payslip.tax or Decimal('0')
            cash_advance = payslip.cash_advance or Decimal('0')
            other_deductions = payslip.other_deductions or Decimal('0')
            net_pay = payslip.net_pay or Decimal('0')

            totals_gross += gross_pay
            totals_net += net_pay

            writer.writerow([
                payslip.employee.full_name,
                payslip.employee.role_display_name,
                payslip.employee.branch.name if payslip.employee.branch else '',
                f"{base_salary:.2f}",
                f"{overtime_pay:.2f}",
                f"{holiday_pay:.2f}",
                f"{bonus:.2f}",
                f"{staff_allowance:.2f}",
                f"{gross_pay:.2f}",
                f"{sss:.2f}",
                f"{philhealth:.2f}",
                f"{pagibig:.2f}",
                f"{tax:.2f}",
                f"{cash_advance:.2f}",
                f"{other_deductions:.2f}",
                f"{net_pay:.2f}",
                payslip.get_status_display()
            ])
        except Exception:
            # Skip payslips with errors
            continue

    # Add summary row
    writer.writerow([])  # Blank row
    writer.writerow(['TOTALS', '', '', '', '', '', '', '',
                     f"{totals_gross:.2f}", '', '', '', '',
                     '', '', f"{totals_net:.2f}", ''])

    # Log the export
    try:
        from payroll.models import PayrollAuditLog
        PayrollAuditLog.log(
            user=request.user,
            action_type=PayrollAuditLog.ActionType.SYSTEM_EXPORT,
            description=f"Exported {len(payslips)} payslips to CSV for {period.period_display}",
            payroll_period=period,
            metadata={'format': 'CSV', 'employee_count': len(payslips)}
        )
    except Exception:
        pass

    messages.success(request, f'Exported {len(payslips)} payslips to CSV.')

    return response


@login_required
@module_permission_required('payroll', 'MANAGE')
def export_payslips_excel(request, period_id):
    """Export payslips to Excel format (.xlsx)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from django.http import HttpResponse

    period = get_object_or_404(PayrollPeriod, id=period_id)

    # Get payslips safely - ID first approach
    payslips = []
    try:
        payslip_ids = list(period.payslips.values_list('id', flat=True))
        for ps_id in payslip_ids:
            try:
                ps = Payslip.objects.select_related(
                    'employee', 'employee__branch').get(id=ps_id)
                payslips.append(ps)
            except Exception:
                continue
    except Exception:
        payslips = []

    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = 'Payslips'

    # Define styles
    header_fill = PatternFill(start_color='009688',
                              end_color='009688', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF', size=11)
    total_fill = PatternFill(start_color='E0F2F1',
                             end_color='E0F2F1', fill_type='solid')
    total_font = Font(bold=True, size=11)
    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    # Add title
    ws['A1'] = f"Payroll Report - {period.period_display}"
    ws['A1'].font = Font(bold=True, size=14)
    ws.merge_cells('A1:Q1')

    # Add headers
    headers = ['Employee Name', 'Position', 'Branch', 'Base Salary',
               'Overtime Pay', 'Holiday Pay', 'Bonus', 'Staff Allowance',
               'Gross Pay', 'SSS', 'PhilHealth', 'PAG-IBIG', 'Tax',
               'Cash Advance', 'Other Ded.', 'Net Pay', 'Status']

    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=3, column=col, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = border

    # Set column widths
    column_widths = [20, 15, 15, 12, 12, 12, 10,
                     12, 12, 10, 12, 10, 10, 12, 12, 12, 10]
    for col, width in enumerate(column_widths, 1):
        ws.column_dimensions[chr(64 + col)].width = width

    # Add data rows with error handling
    row = 4
    totals_gross = Decimal('0')
    totals_net = Decimal('0')

    for payslip in payslips:
        try:
            # Get decimal values with defaults
            base_salary = payslip.base_salary or Decimal('0')
            overtime_pay = payslip.overtime_pay or Decimal('0')
            holiday_pay = payslip.holiday_pay or Decimal('0')
            bonus = payslip.bonus or Decimal('0')
            staff_allowance = payslip.staff_allowance or Decimal('0')
            gross_pay = payslip.gross_pay or Decimal('0')
            sss = payslip.sss or Decimal('0')
            philhealth = payslip.philhealth or Decimal('0')
            pagibig = payslip.pagibig or Decimal('0')
            tax = payslip.tax or Decimal('0')
            cash_advance = payslip.cash_advance or Decimal('0')
            other_deductions = payslip.other_deductions or Decimal('0')
            net_pay = payslip.net_pay or Decimal('0')

            totals_gross += gross_pay
            totals_net += net_pay

            ws.cell(row=row, column=1,
                    value=payslip.employee.full_name).border = border
            ws.cell(row=row, column=2,
                    value=payslip.employee.role_display_name).border = border
            ws.cell(row=row, column=3,
                    value=payslip.employee.branch.name if payslip.employee.branch else '').border = border
            ws.cell(row=row, column=4, value=float(
                base_salary)).border = border
            ws.cell(row=row, column=5, value=float(
                overtime_pay)).border = border
            ws.cell(row=row, column=6, value=float(
                holiday_pay)).border = border
            ws.cell(row=row, column=7, value=float(bonus)).border = border
            ws.cell(row=row, column=8, value=float(staff_allowance)).border = border
            ws.cell(row=row, column=9, value=float(gross_pay)).border = border
            ws.cell(row=row, column=10, value=float(sss)).border = border
            ws.cell(row=row, column=11, value=float(
                philhealth)).border = border
            ws.cell(row=row, column=12, value=float(pagibig)).border = border
            ws.cell(row=row, column=13, value=float(tax)).border = border
            ws.cell(row=row, column=14, value=float(
                cash_advance)).border = border
            ws.cell(row=row, column=15, value=float(
                other_deductions)).border = border
            ws.cell(row=row, column=16, value=float(net_pay)).border = border
            ws.cell(row=row, column=17,
                    value=payslip.get_status_display()).border = border
            row += 1
        except Exception:
            # Skip payslips with errors
            continue

    # Add totals row
    total_row = row + 1
    ws.cell(row=total_row, column=1, value='TOTALS').font = total_font
    ws.cell(row=total_row, column=1).fill = total_fill
    ws.cell(row=total_row, column=9, value=float(
        totals_gross)).font = total_font
    ws.cell(row=total_row, column=9).fill = total_fill
    ws.cell(row=total_row, column=16, value=float(
        totals_net)).font = total_font
    ws.cell(row=total_row, column=16).fill = total_fill

    # Format as currency
    for row_cells in ws.iter_rows(min_row=4, max_row=total_row, min_col=4, max_col=16):
        for cell in row_cells:
            if cell.value and isinstance(cell.value, (int, float)):
                cell.number_format = '#,##0.00'

    # Create response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="payslips_{period.period_display}.xlsx"'

    wb.save(response)

    # Log the export
    try:
        from payroll.models import PayrollAuditLog
        PayrollAuditLog.log(
            user=request.user,
            action_type=PayrollAuditLog.ActionType.SYSTEM_EXPORT,
            description=f"Exported {len(payslips)} payslips to Excel for {period.period_display}",
            payroll_period=period,
            metadata={'format': 'XLSX', 'employee_count': len(payslips)}
        )
    except Exception:
        pass

    messages.success(request, f'Exported {len(payslips)} payslips to Excel.')

    return response


# ═══════════════════════════════════════════════════════════════════
#               EMAIL PAYSLIPS FEATURE
# ═══════════════════════════════════════════════════════════════════

@login_required
@module_permission_required('payroll', 'MANAGE')
def send_payslip_email(request, payslip_id):
    """Send the printable payslip PDF to one employee."""
    from payroll.email_service import send_payslip_email as deliver_payslip_email

    if request.method != 'POST':
        return redirect('payroll:payslips', period_id=get_object_or_404(Payslip, id=payslip_id).payroll_period_id)

    payslip = get_object_or_404(
        Payslip.objects.select_related('employee', 'payroll_period'),
        id=payslip_id
    )

    # Check if employee has email
    if not payslip.employee.email:
        messages.error(
            request, f'{payslip.employee.full_name} does not have an email address.')
        return redirect('payroll:payslips', period_id=payslip.payroll_period.id)

    try:
        sent, reason = deliver_payslip_email(payslip, force=True)
        if not sent:
            messages.error(request, f'Failed to send email: {reason}')
            return redirect('payroll:payslips', period_id=payslip.payroll_period.id)

        from payroll.models import PayrollAuditLog
        PayrollAuditLog.log(
            user=request.user,
            action_type=PayrollAuditLog.ActionType.SYSTEM_EXPORT,
            description=f"Sent payslip email to {payslip.employee.full_name} ({payslip.employee.email})",
            payslip=payslip,
            payroll_period=payslip.payroll_period,
            staff_member=payslip.employee,
            metadata={'email': payslip.employee.email}
        )

        messages.success(request, f'Payslip PDF sent to {payslip.employee.email}')

    except Exception as e:
        messages.error(request, f'Failed to send email: {str(e)}')

    return redirect('payroll:payslips', period_id=payslip.payroll_period.id)


@login_required
@module_permission_required('payroll', 'MANAGE')
def send_payslips_bulk(request, period_id):
    """Send printable payslip PDFs to all employees in a period."""
    from payroll.email_service import send_payslip_email as deliver_payslip_email

    period = get_object_or_404(PayrollPeriod, id=period_id)

    payslips = period.payslips.select_related('employee', 'payroll_period').filter(
        employee__email__isnull=False
    ).exclude(employee__email='')

    sent_count = 0
    failed_count = 0

    for payslip in payslips:
        try:
            sent, _ = deliver_payslip_email(payslip, force=True)
            if sent:
                sent_count += 1
            else:
                failed_count += 1
        except Exception:
            failed_count += 1

    # Log the bulk send action
    try:
        from payroll.models import PayrollAuditLog
        PayrollAuditLog.log(
            user=request.user,
            action_type=PayrollAuditLog.ActionType.SYSTEM_EXPORT,
            description=f"Sent {sent_count} payslip emails for {period.period_display} ({failed_count} failed)",
            payroll_period=period,
            metadata={'sent': sent_count, 'failed': failed_count}
        )
    except Exception:
        pass

    if sent_count > 0:
        messages.success(request, f'Sent {sent_count} payslip emails.')
    if failed_count > 0:
        messages.warning(request, f'{failed_count} emails failed to send.')

    return redirect('payroll:payslips', period_id=period.id)
