"""Views for Attendance and Biometrics Management."""
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count, Sum
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
import logging

from accounts.decorators import admin_only
from employees.models import StaffMember, VetSchedule
from branches.models import Branch
from .models import (
    BiometricDevice,
    AttendanceLog,
    DailyAttendance,
    MonthlyAttendanceSummary,
)
from .forms import (
    BiometricDeviceForm,
    AttendanceImportForm,
    DailyAttendanceForm,
    AttendanceFilterForm,
)
from .services import AttendanceImportService, AttendanceProcessor

logger = logging.getLogger(__name__)


# ─────────────────── DASHBOARD ───────────────────
@login_required
@admin_only
def attendance_dashboard(request):
    """Monthly attendance import dashboard for payroll."""
    # Get recent imports
    recent_logs = AttendanceLog.objects.filter(
        sync_status='PENDING'
    ).order_by('-imported_at')[:5]
    
    context = {
        'recent_logs': recent_logs,
    }
    
    return render(request, 'attendance/dashboard.html', context)


# ─────────────────── DEVICE MANAGEMENT ───────────────────
@login_required
@admin_only
def device_list(request):
    """List all biometric devices."""
    devices = BiometricDevice.objects.all()
    
    context = {
        'devices': devices,
        'page_title': 'Biometric Devices',
    }
    
    return render(request, 'attendance/device_list.html', context)


@login_required
@admin_only
def device_create(request):
    """Create a new biometric device."""
    if request.method == 'POST':
        form = BiometricDeviceForm(request.POST)
        if form.is_valid():
            device = form.save()
            messages.success(request, f'Device "{device.device_name}" created successfully.')
            return redirect('attendance:device_list')
    else:
        form = BiometricDeviceForm()
    
    context = {
        'form': form,
        'page_title': 'Add Biometric Device',
    }
    
    return render(request, 'attendance/device_form.html', context)


@login_required
@admin_only
def device_edit(request, device_id):
    """Edit a biometric device."""
    device = get_object_or_404(BiometricDevice, id=device_id)
    
    if request.method == 'POST':
        form = BiometricDeviceForm(request.POST, instance=device)
        if form.is_valid():
            form.save()
            messages.success(request, f'Device "{device.device_name}" updated successfully.')
            return redirect('attendance:device_list')
    else:
        form = BiometricDeviceForm(instance=device)
    
    context = {
        'form': form,
        'device': device,
        'page_title': f'Edit Device: {device.device_name}',
    }
    
    return render(request, 'attendance/device_form.html', context)


@login_required
@admin_only
def device_detail(request, device_id):
    """View device metadata and legacy punch history."""
    device = get_object_or_404(BiometricDevice, id=device_id)
    
    # Recent logs
    recent_logs = device.attendance_logs.order_by('-punch_datetime')[:20]
    
    # Statistics
    total_logs = device.attendance_logs.count()
    matched_logs = device.attendance_logs.filter(sync_status='MATCHED').count()
    unmatched_logs = device.attendance_logs.filter(sync_status='UNMATCHED').count()
    
    context = {
        'device': device,
        'recent_logs': recent_logs,
        'total_logs': total_logs,
        'matched_logs': matched_logs,
        'unmatched_logs': unmatched_logs,
        'device_edit_url': f'/attendance/devices/{device.id}/edit/',
        'page_title': f'Device: {device.device_name}',
    }
    
    return render(request, 'attendance/device_detail.html', context)


# ─────────────────── ATTENDANCE IMPORT ───────────────────
@login_required
@admin_only
def attendance_import(request):
    """Import one monthly summary attendance file for payroll."""
    if request.method == 'POST':
        form = AttendanceImportForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                service = AttendanceImportService()
                records = form.get_records()
                imported, matched, errors = service.import_summary_records(
                    records,
                    source_filename=form.cleaned_data['import_file'].name,
                    uploaded_by=request.user,
                )
                
                message = (
                    f'Monthly import completed: {imported} records imported, '
                    f'{matched} matched to staff, {errors} errors.'
                )
                messages.success(request, message)
                logger.info(message)
                
                if records and all(record.get('Report Start') for record in records if isinstance(record, dict)):
                    report_month = service.parse_date_value(records[0].get('Report Start'))
                    if report_month:
                        return redirect(
                            f'/attendance/review/?year={report_month.year}&month={report_month.month}'
                        )
                return redirect('attendance:import')
                
            except Exception as e:
                logger.error(f'Import error: {str(e)}')
                messages.error(request, f'Import failed: {str(e)}')
    else:
        form = AttendanceImportForm()
    
    context = {
        'form': form,
        'page_title': 'Import Attendance Data',
    }
    
    return render(request, 'attendance/import.html', context)


# ─────────────────── ATTENDANCE REVIEW ───────────────────
@login_required
@admin_only
def attendance_review(request):
    """Review and approve imported monthly attendance summaries."""
    year = _attendance_query_int(request.GET.get('year'), timezone.now().year, 2020, 2100)
    month = _attendance_query_int(request.GET.get('month'), timezone.now().month, 1, 12)
    summaries = MonthlyAttendanceSummary.objects.filter(
        period_start__year=year,
        period_start__month=month,
    ).select_related('staff', 'uploaded_by', 'approved_by').order_by('staff__last_name', 'staff__first_name')

    if request.method == 'POST':
        if summaries.filter(review_status=MonthlyAttendanceSummary.ReviewStatus.LOCKED).exists():
            messages.error(request, 'This attendance month is already locked.')
        elif not summaries.exists():
            messages.error(request, 'No imported attendance summary exists for this month.')
        else:
            summaries.update(
                review_status=MonthlyAttendanceSummary.ReviewStatus.APPROVED,
                approved_by=request.user,
                approved_at=timezone.now(),
            )
            messages.success(request, f'Attendance for {month:02d}/{year} was approved for payroll.')
        return redirect(f'/attendance/review/?year={year}&month={month}')

    total_records = summaries.count()
    approved_records = summaries.filter(review_status__in=[MonthlyAttendanceSummary.ReviewStatus.APPROVED, MonthlyAttendanceSummary.ReviewStatus.LOCKED]).count()
    unapproved_records = total_records - approved_records
    context = {
        'monthly_summaries': summaries,
        'selected_year': year,
        'selected_month': month,
        'total_records': total_records,
        'approved_records': approved_records,
        'unapproved_records': unapproved_records,
        'can_approve': total_records > 0 and unapproved_records > 0,
        'page_title': 'Review Monthly Attendance',
    }
    return render(request, 'attendance/review.html', context)


@login_required
@admin_only
def attendance_edit(request, attendance_id):
    """Edit a daily attendance record."""
    attendance = get_object_or_404(DailyAttendance, id=attendance_id)
    
    if request.method == 'POST':
        form = DailyAttendanceForm(request.POST, instance=attendance)
        if form.is_valid():
            attendance = form.save(commit=False)
            attendance.is_manually_adjusted = True
            attendance.adjusted_by = request.user
            attendance.save()
            messages.success(request, 'Attendance record updated.')
            return redirect('attendance:review')
    else:
        form = DailyAttendanceForm(instance=attendance)
    
    # Get schedule for reference
    schedule = VetSchedule.objects.filter(
        staff=attendance.staff,
        date=attendance.attendance_date,
        is_available=True
    ).first()
    
    context = {
        'form': form,
        'attendance': attendance,
        'schedule': schedule,
        'page_title': f'Edit Attendance: {attendance.staff.full_name}',
    }
    
    return render(request, 'attendance/attendance_edit.html', context)


@login_required
@admin_only
@require_http_methods(["POST"])
def attendance_approve(request, attendance_id):
    """Approve an attendance record."""
    attendance = get_object_or_404(DailyAttendance, id=attendance_id)
    attendance.is_approved = True
    attendance.approved_by = request.user
    attendance.approved_at = timezone.now()
    attendance.save()
    messages.success(request, f'Attendance for {attendance.staff.full_name} approved.')
    return redirect('attendance:review')

# ─────────────────── REPORTS ───────────────────
def _attendance_query_int(value, default, minimum, maximum):
    """Parse formatted report query values without allowing invalid dates."""
    try:
        parsed = int(str(value).replace(',', '').strip())
    except (TypeError, ValueError):
        return default
    return parsed if minimum <= parsed <= maximum else default


@login_required
@admin_only
def attendance_summary(request):
    """Monthly attendance summary report."""
    # Get current month or specified month.
    current_year = timezone.now().year
    year = _attendance_query_int(request.GET.get('year'), current_year, 2020, 2100)
    month = _attendance_query_int(request.GET.get('month'), timezone.now().month, 1, 12)
    branch_id = request.GET.get('branch') or ''
    
    # Calculate date range
    start_date = timezone.datetime(year, month, 1).date()
    if month == 12:
        end_date = timezone.datetime(year + 1, 1, 1).date() - timedelta(days=1)
    else:
        end_date = timezone.datetime(year, month + 1, 1).date() - timedelta(days=1)
    
    # Get staff and optionally scope the report to a branch.
    staff_members = StaffMember.objects.filter(
        is_active=True,
    ).exclude(
        user__assigned_role__code='superadmin'
    ).select_related('user')
    if branch_id:
        staff_members = staff_members.filter(branch_id=branch_id)
    staff_members = staff_members.order_by('last_name', 'first_name')
    
    # Build summary
    summary_data = []
    total_scheduled_days = 0
    total_present_days = 0
    total_overtime_minutes = 0
    for staff in staff_members:
        monthly_summary = MonthlyAttendanceSummary.objects.filter(
            staff=staff,
            period_start__year=year,
            period_start__month=month,
        ).order_by('-period_end').first()
        attendance_records = DailyAttendance.objects.filter(
            staff=staff,
            attendance_date__range=[start_date, end_date],
        )
        
        present_days = monthly_summary.attendance_days if monthly_summary else attendance_records.filter(is_present=True).count()
        absent_days = monthly_summary.absence_days if monthly_summary else attendance_records.filter(is_present=False).count()
        late_days = monthly_summary.late_days if monthly_summary else attendance_records.filter(status='LATE').count()
        total_late_minutes = attendance_records.aggregate(
            total=Sum('late_minutes')
        )['total'] or 0
        staff_overtime_minutes = (
            monthly_summary.overtime_hours * Decimal('60')
            if monthly_summary else attendance_records.aggregate(
                total=Sum('overtime_minutes')
            )['total'] or 0
        )

        scheduled_days = monthly_summary.working_days if monthly_summary else VetSchedule.objects.filter(
            staff=staff,
            date__range=[start_date, end_date],
            is_available=True,
        ).count()
        denominator = scheduled_days or (present_days + absent_days)
        attendance_rate = (present_days / denominator * 100) if denominator else 0
        total_scheduled_days += scheduled_days
        total_present_days += present_days
        total_overtime_minutes += staff_overtime_minutes

        summary_data.append((staff, {
            'working_days': scheduled_days,
            'days_present': present_days,
            'days_absent': absent_days,
            'days_late': late_days,
            'total_late_minutes': total_late_minutes,
            'total_overtime_hours': Decimal(staff_overtime_minutes) / Decimal('60'),
            'sick_hours': monthly_summary.sick_hours if monthly_summary else Decimal('0'),
            'leave_hours': monthly_summary.leave_hours if monthly_summary else Decimal('0'),
            'daily_salary': monthly_summary.daily_salary if monthly_summary else Decimal('0'),
            'overtime_pay': monthly_summary.overtime_pay if monthly_summary else Decimal('0'),
            'allowances': monthly_summary.allowances if monthly_summary else Decimal('0'),
            'charges': monthly_summary.charges if monthly_summary else Decimal('0'),
            'real_pay': monthly_summary.real_pay if monthly_summary else Decimal('0'),
            'attendance_rate': attendance_rate,
        }))

    total_working_days = total_scheduled_days
    avg_attendance_rate = (
        total_present_days / total_scheduled_days * 100
        if total_scheduled_days else 0
    )
    
    context = {
        'summary_data': summary_data,
        'year': year,
        'month': month,
        'start_date': start_date,
        'end_date': end_date,
        'year_choices': range(current_year - 2, current_year + 2),
        'month_choices': [(index, timezone.datetime(2000, index, 1).strftime('%B')) for index in range(1, 13)],
        'branches': Branch.objects.filter(is_active=True),
        'selected_year': year,
        'selected_month': month,
        'selected_branch': int(branch_id) if branch_id.isdigit() else '',
        'total_working_days': total_working_days,
        'avg_attendance_rate': avg_attendance_rate,
        'total_overtime_hours': Decimal(total_overtime_minutes) / Decimal('60'),
        'page_title': f'Attendance Summary - {start_date.strftime("%B %Y")}',
    }
    
    return render(request, 'attendance/summary.html', context)
