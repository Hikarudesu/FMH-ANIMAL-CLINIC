"""Business logic for monthly attendance summary imports."""
from datetime import date, datetime, timedelta
from decimal import Decimal
import logging
import re

from dateutil import parser as date_parser
from django.db.models import Sum

from employees.models import StaffMember
from settings.utils import get_setting
from .models import AttendanceUpload, DailyAttendance, MonthlyAttendanceSummary
from .calculation_engine import OvertimeCalculator

logger = logging.getLogger(__name__)


class AttendanceImportService:
    """Import monthly summary records matched by staff biometric ID."""

    @staticmethod
    def clear_monthly_import_data(period_start, period_end):
        """Remove all daily and summary attendance rows for a calendar month."""
        daily_records = DailyAttendance.objects.filter(
            attendance_date__year=period_start.year,
            attendance_date__month=period_start.month,
        )
        summaries = MonthlyAttendanceSummary.objects.filter(
            period_start__year=period_start.year,
            period_start__month=period_start.month,
        )
        daily_deleted, _ = daily_records.delete()
        summary_deleted, _ = summaries.delete()
        return daily_deleted, summary_deleted

    @staticmethod
    def _normalize_biometric_id(value):
        """Normalize scanner IDs without discarding meaningful leading zeros."""
        if value in (None, ''):
            return ''
        text = str(value).strip()
        if text.endswith('.0') and text[:-2].isdigit():
            return text[:-2]
        return text

    @staticmethod
    def _extract_biometric_id(record):
        value = AttendanceImportService._get_first_matching_value(
            record,
            {
                'biometric id', 'biometrics id', 'biometric number', 'biometric no',
                'staff biometric id', 'employee id', 'employee number', 'employee no',
                'employee code', 'user id', 'staff id', 'staff number', 'staff no', 'staff code',
            }
        )
        if value in (None, ''):
            return None
        return AttendanceImportService._normalize_biometric_id(value)

    @staticmethod
    def _find_staff_by_biometric_id(value):
        biometric_id = AttendanceImportService._normalize_biometric_id(value)
        if not biometric_id:
            return None

        staff = StaffMember.objects.filter(
            biometric_id=biometric_id,
            is_active=True,
        ).first()
        if staff:
            return staff

        # Spreadsheet readers can turn an ID such as 00011 into 11. Match
        # numeric IDs by value only when an exact match was not found.
        if biometric_id.isdigit():
            numeric_id = biometric_id.lstrip('0') or '0'
            for candidate in StaffMember.objects.filter(is_active=True).exclude(
                biometric_id__isnull=True,
            ):
                candidate_id = AttendanceImportService._normalize_biometric_id(candidate.biometric_id)
                if candidate_id.isdigit() and (candidate_id.lstrip('0') or '0') == numeric_id:
                    return candidate
        return None

    @staticmethod
    def get_unmatched_biometric_ids(records):
        """Return biometric IDs that do not map to an active staff member."""
        unmatched = []
        seen = set()
        for record in records:
            if not isinstance(record, dict):
                continue
            biometric_id = AttendanceImportService._extract_biometric_id(record)
            if not biometric_id or biometric_id in seen:
                continue
            if not AttendanceImportService._find_staff_by_biometric_id(biometric_id):
                unmatched.append(biometric_id)
                seen.add(biometric_id)
        return unmatched

    @staticmethod
    def _normalize_key(value):
        return re.sub(r'[^a-z0-9]+', ' ', str(value or '').strip().lower()).strip()

    @staticmethod
    def _coerce_decimal(value):
        if value in (None, '', 'None'):
            return Decimal('0')
        try:
            return Decimal(str(value).replace(',', ''))
        except Exception:
            return Decimal('0')

    @staticmethod
    def _get_first_matching_value(record, aliases):
        for key, value in record.items():
            if AttendanceImportService._normalize_key(key) in aliases:
                return value
        return None

    @staticmethod
    def _resolve_staff_from_record(record):
        for key, value in record.items():
            if AttendanceImportService._normalize_key(key) in {
                'biometric id', 'biometrics id', 'staff biometric id',
                'biometric number', 'biometric no', 'employee id', 'employee number',
                'employee no', 'employee code', 'user id', 'staff id', 'staff number', 'staff no',
                'staff code', 'timein', 'timeout',
            } and value not in (None, ''):
                staff = AttendanceImportService._find_staff_by_biometric_id(value)
                if staff:
                    return staff, 'biometric_id'
        return None, None

    @staticmethod
    def parse_time_value(value):
        if value in (None, '', 'None'):
            return None
        if isinstance(value, datetime):
            return value.time()
        try:
            return date_parser.parse(str(value).strip()).time()
        except (TypeError, ValueError, OverflowError):
            return None

    @staticmethod
    def parse_date_value(value):
        if value in (None, '', 'None'):
            return None
        if hasattr(value, 'date'):
            return value.date()
        try:
            return date_parser.parse(str(value).strip()).date()
        except (TypeError, ValueError, OverflowError):
            return None

    def import_summary_records(self, records, source_filename='', uploaded_by=None, skip_duplicates=False):
        """Import one monthly summary per staff member."""
        months = set()
        month_keys = set()
        for record in records:
            if not isinstance(record, dict):
                continue
            report_date = self.parse_date_value(record.get('Report Start'))
            if report_date:
                months.add((report_date.year, report_date.month))
                month_keys.add((report_date.year, report_date.month))
            else:
                report_date = self.parse_date_value(self._get_first_matching_value(
                    record, {'date', 'attendance date', 'work date'}
                ))
                if report_date:
                    months.add((report_date.year, report_date.month))
                    month_keys.add((report_date.year, report_date.month))
        if len(months) > 1:
            raise ValueError('Upload one month per attendance update.')

        if skip_duplicates and month_keys:
            for year, month in month_keys:
                if MonthlyAttendanceSummary.objects.filter(
                    period_start__year=year,
                    period_start__month=month,
                ).exists() or AttendanceUpload.objects.filter(
                    period_start__year=year,
                    period_start__month=month,
                ).exists():
                    raise ValueError("This month's attendance has already been uploaded.")

        imported = matched = errors = 0
        self.import_results = []
        summary_periods = set()
        detailed_dates_by_staff = {}
        for record in records:
            if not isinstance(record, dict) or 'Date' not in record:
                continue
            detailed_staff, _ = self._resolve_staff_from_record(record)
            detailed_date = self.parse_date_value(record.get('Date'))
            if detailed_staff and detailed_date:
                detailed_dates_by_staff.setdefault(detailed_staff.pk, set()).add(detailed_date)
        for record in records:
            if not isinstance(record, dict):
                continue
            try:
                staff, _ = self._resolve_staff_from_record(record)
                if not staff:
                    biometric_id = self._extract_biometric_id(record)
                    self.import_results.append({'status': 'unmatched', 'biometric_id': biometric_id})
                    errors += 1
                    continue

                if str(record.get('Summary', '')).upper() == 'MONTHLY':
                    period_start = self.parse_date_value(record.get('Report Start'))
                    period_end = self.parse_date_value(record.get('Report End'))
                    if not period_start or not period_end:
                        errors += 1
                        continue
                    detailed_dates = detailed_dates_by_staff.get(staff.pk, set())
                    if period_start.day > 1 and any(
                        period_start <= detailed_date <= period_end
                        for detailed_date in detailed_dates
                    ):
                        continue
                    summary, created = MonthlyAttendanceSummary.objects.update_or_create(
                        staff=staff,
                        period_start=period_start,
                        period_end=period_end,
                        defaults={
                            'working_days': int(self._coerce_decimal(self._get_first_matching_value(record, {
                                'working days', 'work days', 'scheduled days',
                            }))),
                            'attendance_days': int(self._coerce_decimal(self._get_first_matching_value(record, {
                                'attendance days', 'attended days', 'days present', 'present days',
                            }))),
                            'absence_days': int(self._coerce_decimal(self._get_first_matching_value(record, {
                                'absences days', 'absence days', 'absent days', 'days absent',
                            }))),
                            'late_days': int(self._coerce_decimal(self._get_first_matching_value(record, {'late num', 'late number'}))),
                            'overtime_hours': self._coerce_decimal(self._get_first_matching_value(record, {
                                'overtime hours', 'overtime hour', 'ot hours', 'ot hour',
                            })),
                            'sick_hours': self._coerce_decimal(self._get_first_matching_value(record, {'sick hours'})),
                            'leave_hours': self._coerce_decimal(self._get_first_matching_value(record, {'leave hours'})),
                            # Compensation is calculated by payroll from the
                            # employee record and payroll settings, never from
                            # biometric exports.
                            'daily_salary': Decimal('0'),
                            'overtime_pay': Decimal('0'),
                            'charges': Decimal('0'),
                            'source_filename': source_filename,
                            'uploaded_by': uploaded_by,
                            'review_status': MonthlyAttendanceSummary.ReviewStatus.IMPORTED,
                            'approved_by': None,
                            'approved_at': None,
                        },
                    )
                    summary_periods.add((period_start.year, period_start.month))
                    self.import_results.append({'status': 'updated' if not created else 'imported', 'staff': staff.full_name, 'biometric_id': staff.biometric_id})
                    imported += 1
                    matched += 1
                    continue

                attendance_date = self.parse_date_value(self._get_first_matching_value(
                    record, {'date', 'attendance date', 'work date'}
                ))
                if not attendance_date:
                    errors += 1
                    continue
                morning_in = self.parse_time_value(record.get('Morning In'))
                morning_out = self.parse_time_value(record.get('Morning Out'))
                afternoon_in = self.parse_time_value(record.get('Afternoon In'))
                afternoon_out = self.parse_time_value(record.get('Afternoon Out'))
                ot_in = self.parse_time_value(record.get('Overtime In'))
                ot_out = self.parse_time_value(record.get('Overtime Out'))
                check_in = self.parse_time_value(self._get_first_matching_value(record, {'check in', 'time in', 'clock in', 'timein'})) or morning_in
                check_out = self.parse_time_value(self._get_first_matching_value(record, {'check out', 'time out', 'clock out', 'timeout'})) or afternoon_out
                daily, _ = DailyAttendance.objects.get_or_create(staff=staff, attendance_date=attendance_date)
                daily.check_in = check_in
                daily.check_out = check_out
                daily.morning_in = morning_in
                daily.morning_out = morning_out
                daily.afternoon_in = afternoon_in
                daily.afternoon_out = afternoon_out
                daily.ot_in = ot_in
                daily.ot_out = ot_out
                daily.is_present = bool(check_in and check_out)
                daily.status = 'PRESENT' if daily.is_present else 'ABSENT'
                daily.four_punch_complete = all((morning_in, morning_out, afternoon_in, afternoon_out))
                daily.punch_validation_status = 'PASS' if daily.four_punch_complete else 'FAIL'
                daily.total_work_minutes = int(self._coerce_decimal(self._get_first_matching_value(record, {'total work minutes', 'worked minutes'})))
                daily.late_minutes = int(self._coerce_decimal(self._get_first_matching_value(record, {'late minutes', 'minutes late'})))
                daily.overtime_minutes = int(self._coerce_decimal(self._get_first_matching_value(record, {'overtime minutes', 'ot minutes'})))
                if ot_in and ot_out:
                    daily.ot_hours_calculated = OvertimeCalculator.calculate_hours_between(
                        datetime.combine(attendance_date, ot_in),
                        datetime.combine(attendance_date, ot_out),
                    )
                    daily.overtime_minutes = int(daily.ot_hours_calculated * Decimal('60'))
                daily.is_approved = True
                daily.save()
                summary_periods.add((attendance_date.year, attendance_date.month))
                imported += 1
                matched += 1
            except Exception as exc:
                errors += 1
                logger.exception('Error importing attendance summary record: %s', exc)
        for year, month in summary_periods:
            summaries = MonthlyAttendanceSummary.objects.filter(
                period_start__year=year,
                period_start__month=month,
            ).select_related('staff')
            for summary in summaries:
                overtime_minutes = DailyAttendance.objects.filter(
                    staff=summary.staff,
                    attendance_date__year=year,
                    attendance_date__month=month,
                ).aggregate(total=Sum('overtime_minutes'))['total'] or 0
                summary.overtime_hours = Decimal(overtime_minutes) / Decimal('60')
                summary.daily_salary = (
                    Decimal(str(summary.staff.salary or 0)) / Decimal(str(summary.working_days))
                    if summary.working_days else Decimal('0')
                )
                hourly_rate = self._coerce_decimal(get_setting('payroll_default_overtime_pay_per_hour', 120))
                summary.overtime_pay = summary.overtime_hours * hourly_rate
                summary.charges = Decimal('0')
                summary.save(update_fields=['overtime_hours', 'daily_salary', 'overtime_pay', 'charges'])

        return imported, matched, errors


class AttendanceProcessor:
    """Payroll metrics for legacy daily attendance records."""

    @staticmethod
    def reconcile_with_schedule(staff, from_date, to_date):
        return 0

    @staticmethod
    def calculate_payroll_metrics(staff, month, year):
        start_date = date(year, month, 1)
        end_date = date(year + 1, 1, 1) - timedelta(days=1) if month == 12 else date(year, month + 1, 1) - timedelta(days=1)
        records = DailyAttendance.objects.filter(
            staff=staff,
            attendance_date__range=[start_date, end_date],
            is_approved=True,
        )
        overtime_total = records.aggregate(total=Sum('overtime_minutes'))['total'] or 0
        late_total = records.aggregate(total=Sum('late_minutes'))['total'] or 0
        return {
            'approved_records': records.count(),
            'days_present': records.filter(is_present=True).count(),
            'days_absent': records.filter(is_present=False).count(),
            'days_late': records.filter(status='LATE').count(),
            'total_overtime_minutes': overtime_total,
            'total_late_minutes': late_total,
            'total_overtime_hours': Decimal(overtime_total) / Decimal('60'),
        }
