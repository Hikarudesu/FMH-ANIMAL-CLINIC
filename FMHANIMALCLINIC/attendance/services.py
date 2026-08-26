"""Business logic for monthly attendance summary imports."""
from datetime import date, datetime, timedelta
from decimal import Decimal
import logging
import re

from dateutil import parser as date_parser
from django.db.models import Sum

from employees.models import StaffMember
from .models import DailyAttendance, MonthlyAttendanceSummary

logger = logging.getLogger(__name__)


class AttendanceImportService:
    """Import monthly summary records matched by staff biometric ID."""

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
                'employee id', 'employee code', 'staff id', 'staff code',
            } and value not in (None, ''):
                staff = StaffMember.objects.filter(
                    biometric_id=str(value).strip(), is_active=True
                ).first()
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

    def import_summary_records(self, records, source_filename='', uploaded_by=None, skip_duplicates=True):
        """Import one monthly summary per staff member."""
        months = set()
        for record in records:
            if not isinstance(record, dict):
                continue
            report_date = self.parse_date_value(record.get('Report Start'))
            if report_date:
                months.add((report_date.year, report_date.month))
            else:
                report_date = self.parse_date_value(self._get_first_matching_value(
                    record, {'date', 'attendance date', 'work date'}
                ))
                if report_date:
                    months.add((report_date.year, report_date.month))
        if len(months) > 1:
            raise ValueError('Upload one month per attendance update.')

        imported = matched = errors = 0
        self.import_results = []
        for record in records:
            if not isinstance(record, dict):
                continue
            try:
                staff, _ = self._resolve_staff_from_record(record)
                if not staff:
                    self.import_results.append({'status': 'unmatched', 'biometric_id': self._get_first_matching_value(record, {'biometric id', 'biometrics id', 'employee id', 'staff id'})})
                    errors += 1
                    continue

                if str(record.get('Summary', '')).upper() == 'MONTHLY':
                    period_start = self.parse_date_value(record.get('Report Start'))
                    period_end = self.parse_date_value(record.get('Report End'))
                    if not period_start or not period_end:
                        errors += 1
                        continue
                    summary, created = MonthlyAttendanceSummary.objects.update_or_create(
                        staff=staff,
                        period_start=period_start,
                        period_end=period_end,
                        defaults={
                            'working_days': int(self._coerce_decimal(self._get_first_matching_value(record, {'working days'}))),
                            'attendance_days': int(self._coerce_decimal(self._get_first_matching_value(record, {'attendance days'}))),
                            'absence_days': int(self._coerce_decimal(self._get_first_matching_value(record, {'absences days'}))),
                            'late_days': int(self._coerce_decimal(self._get_first_matching_value(record, {'late num', 'late number'}))),
                            'overtime_hours': self._coerce_decimal(self._get_first_matching_value(record, {'overtime hours'})),
                            'sick_hours': self._coerce_decimal(self._get_first_matching_value(record, {'sick hours'})),
                            'leave_hours': self._coerce_decimal(self._get_first_matching_value(record, {'leave hours'})),
                            'daily_salary': self._coerce_decimal(self._get_first_matching_value(record, {'daily salary'})),
                            'overtime_pay': self._coerce_decimal(self._get_first_matching_value(record, {'overtime pay'})),
                            'allowances': self._coerce_decimal(self._get_first_matching_value(record, {'allowances', 'allowance'})),
                            'charges': self._coerce_decimal(self._get_first_matching_value(record, {'charges', 'charge'})),
                            'real_pay': self._coerce_decimal(self._get_first_matching_value(record, {'real pay'})),
                            'source_filename': source_filename,
                            'uploaded_by': uploaded_by,
                            'review_status': MonthlyAttendanceSummary.ReviewStatus.IMPORTED,
                            'approved_by': None,
                            'approved_at': None,
                        },
                    )
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
                check_in = self.parse_time_value(self._get_first_matching_value(record, {'check in', 'time in', 'clock in'}))
                check_out = self.parse_time_value(self._get_first_matching_value(record, {'check out', 'time out', 'clock out'}))
                daily, _ = DailyAttendance.objects.get_or_create(staff=staff, attendance_date=attendance_date)
                daily.check_in = check_in
                daily.check_out = check_out
                daily.is_present = bool(check_in or check_out)
                daily.status = 'PRESENT' if daily.is_present else 'ABSENT'
                daily.total_work_minutes = int(self._coerce_decimal(self._get_first_matching_value(record, {'total work minutes', 'worked minutes'})))
                daily.late_minutes = int(self._coerce_decimal(self._get_first_matching_value(record, {'late minutes', 'minutes late'})))
                daily.overtime_minutes = int(self._coerce_decimal(self._get_first_matching_value(record, {'overtime minutes', 'ot minutes'})))
                daily.is_approved = True
                daily.save()
                imported += 1
                matched += 1
            except Exception as exc:
                errors += 1
                logger.exception('Error importing attendance summary record: %s', exc)
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
