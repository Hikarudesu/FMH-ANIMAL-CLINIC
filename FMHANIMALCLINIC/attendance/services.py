"""Business logic for monthly attendance summary imports."""
from datetime import date, datetime, timedelta
from decimal import Decimal
import logging
import re
import calendar

from dateutil import parser as date_parser
from django.db.models import Sum

from employees.models import StaffMember
from .models import AttendanceUpload, DailyAttendance, MonthlyAttendanceSummary
from .calculation_engine import (
    FourPunchValidator,
    WorkingDaysCalculator,
    AttendanceCappingEngine,
    OvertimeCalculator,
    AttendanceCalculationEngine,
)

logger = logging.getLogger(__name__)


class AttendanceImportService:
    """Import monthly summary records matched by staff biometric ID."""

    @staticmethod
    def _extract_biometric_id(record):
        value = AttendanceImportService._get_first_matching_value(
            record,
            {
                'biometric id', 'biometrics id', 'biometric number', 'biometric no',
                'staff biometric id', 'employee id', 'employee number', 'employee no',
                'employee code', 'staff id', 'staff number', 'staff no', 'staff code',
                'user id', 'user number', 'user no', 'user code', 'id',
            }
        )
        if value in (None, ''):
            return None
        return str(value).strip()

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
            if not StaffMember.objects.filter(biometric_id=biometric_id, is_active=True).exists():
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

    @staticmethod
    def _resolve_staff_from_record(record):
        identifier_aliases = {
            'biometric id', 'biometrics id', 'staff biometric id',
            'biometric number', 'biometric no', 'employee id', 'employee number',
            'employee no', 'employee code', 'staff id', 'staff number', 'staff no',
            'staff code', 'user id', 'user number', 'user no', 'user code', 'id',
        }
        for key, value in record.items():
            if AttendanceImportService._normalize_key(key) in identifier_aliases and value not in (None, ''):
                identifier = str(value).strip()
                staff = StaffMember.objects.filter(
                    biometric_id=identifier, is_active=True
                ).first()
                if staff:
                    return staff, 'biometric_id'

        name_aliases = {'name', 'employee name', 'staff name', 'user name', 'full name'}
        for key, value in record.items():
            if AttendanceImportService._normalize_key(key) not in name_aliases or value in (None, ''):
                continue
            normalized_name = AttendanceImportService._normalize_key(value)
            for staff in StaffMember.objects.filter(is_active=True):
                if AttendanceImportService._normalize_key(staff.full_name) == normalized_name:
                    return staff, 'name'
        return None, None

    @staticmethod
    def parse_time_value(value):
        if value in (None, '', 'None'):
            return None
        if isinstance(value, datetime):
            return value.time()
        text = str(value).strip()
        if not text:
            return None
        if re.fullmatch(r'\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|am|pm)?', text):
            try:
                return date_parser.parse(text).time()
            except (TypeError, ValueError, OverflowError):
                pass
        try:
            return date_parser.parse(text).time()
        except (TypeError, ValueError, OverflowError):
            return None

    @staticmethod
    def _get_first_matching_value(record, aliases, *, fallback_aliases=None):
        aliases = {AttendanceImportService._normalize_key(alias) for alias in aliases}
        if fallback_aliases:
            aliases.update({AttendanceImportService._normalize_key(alias) for alias in fallback_aliases})
        for key, value in record.items():
            normalized = AttendanceImportService._normalize_key(key)
            if normalized in aliases:
                return value
        return None

    @staticmethod
    def _collect_shift_pairs(record):
        """Collect all complete morning/afternoon punch pairs from a daily attendance row."""
        pairs = []
        candidates = [
            ({'check in', 'time in', 'clock in', 'in time', 'timein', 'login', 'morning in', 'am in', 'morning time in', 'morning check in', 'time in 1', 'in 1', 'shift 1 in'},
             {'check out', 'time out', 'clock out', 'out time', 'timeout', 'logout', 'morning out', 'am out', 'morning time out', 'morning check out', 'time out 1', 'out 1', 'shift 1 out'}),
            ({'afternoon in', 'pm in', 'afternoon time in', 'pm time in', 'time in 2', 'in 2', 'shift 2 in', 'after noon in'},
             {'afternoon out', 'pm out', 'afternoon time out', 'pm time out', 'time out 2', 'out 2', 'shift 2 out', 'after noon out'}),
        ]

        for in_aliases, out_aliases in candidates:
            in_value = None
            out_value = None
            for alias in in_aliases:
                value = AttendanceImportService._get_first_matching_value(record, {alias})
                if value not in (None, ''):
                    in_value = value
                    break
            for alias in out_aliases:
                value = AttendanceImportService._get_first_matching_value(record, {alias})
                if value not in (None, ''):
                    out_value = value
                    break
            if in_value is not None or out_value is not None:
                pairs.append((AttendanceImportService.parse_time_value(in_value), AttendanceImportService.parse_time_value(out_value)))

        if not pairs:
            raw_in = AttendanceImportService._get_first_matching_value(record, {'check in', 'time in', 'clock in', 'in time', 'timein', 'login'})
            raw_out = AttendanceImportService._get_first_matching_value(record, {'check out', 'time out', 'clock out', 'out time', 'timeout', 'logout'})
            if raw_in is not None or raw_out is not None:
                pairs.append((AttendanceImportService.parse_time_value(raw_in), AttendanceImportService.parse_time_value(raw_out)))

        return pairs

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

    @staticmethod
    def clear_monthly_import_data(period_start, period_end=None):
        """Delete every imported attendance row and summary in the calendar month."""
        if not period_start:
            return 0, 0

        month_start = period_start.replace(day=1)
        month_end = period_start.replace(
            day=calendar.monthrange(period_start.year, period_start.month)[1]
        )

        daily_deleted, _ = DailyAttendance.objects.filter(
            attendance_date__range=[month_start, month_end],
        ).delete()
        summary_deleted, _ = MonthlyAttendanceSummary.objects.filter(
            period_start__year=period_start.year,
            period_start__month=period_start.month,
        ).delete()
        return daily_deleted, summary_deleted

    def import_summary_records(self, records, source_filename='', uploaded_by=None, skip_duplicates=True):
        """Import a monthly summary for each staff member.

        Re-importing the same month/year should refresh the existing staff summary
        rather than reject the upload. This supports partial first-half imports that
        are later updated with the second-half data for the same month.

        PRECEDENCE RULE:
        - Detailed daily time records always win over a monthly summary block.
        - Summary values are only used as a fallback when the file contains no daily
          time metadata at all.
        
        PRIORITY LOGIC:
        1. If record has MONTHLY Summary tag and there is no detailed daily punch data in the file → Import as MonthlyAttendanceSummary
        2. If record has date + 4-punch times → Import as DailyAttendance with 4-punch validation
        3. Otherwise → Skip/error
        
        4-PUNCH RULE (STRICT):
        - Attendance REQUIRES: morning_in AND morning_out AND afternoon_in AND afternoon_out
        - If ANY punch is missing → Mark as ABSENT (status='ABSENT', is_present=False)
        """
        months = set()
        month_keys = set()
        has_detailed_daily_time_data = any(
            isinstance(record, dict)
            and (
                record.get('Date')
                or record.get('date')
                or record.get('attendance date')
                or record.get('work date')
            )
            and any(
                record.get(alias) not in (None, '', '-', '--')
                for alias in [
                    'Morning In', 'Morning Out', 'Afternoon In', 'Afternoon Out',
                    'Time In', 'Time Out', 'check in', 'check out', 'morning in', 'morning out',
                    'afternoon in', 'afternoon out', 'timein', 'timeout', 'in time', 'out time',
                    'overtime in', 'overtime out', 'ot in', 'ot out', 'ot_in', 'ot_out'
                ]
            )
            for record in records
        )
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

        imported = matched = errors = 0
        self.import_results = []

        detailed_periods = set()
        for record in records:
            if not isinstance(record, dict):
                continue
            staff, _ = self._resolve_staff_from_record(record)
            if not staff:
                continue

            candidate_date = self.parse_date_value(self._get_first_matching_value(record, {'date', 'attendance date', 'work date'}))
            if not candidate_date:
                candidate_date = self.parse_date_value(record.get('Report Start'))
            if not candidate_date:
                continue

            has_time_values = any(
                record.get(alias) not in (None, '', '-', '--')
                for alias in [
                    'Morning In', 'Morning Out', 'Afternoon In', 'Afternoon Out',
                    'Time In', 'Time Out', 'check in', 'check out', 'morning in', 'morning out',
                    'afternoon in', 'afternoon out', 'timein', 'timeout', 'in time', 'out time',
                    'am in', 'am out', 'pm in', 'pm out', 'morning_time_in', 'morning_time_out',
                    'afternoon_time_in', 'afternoon_time_out',
                    'overtime in', 'overtime out', 'ot in', 'ot out', 'ot_in', 'ot_out'
                ]
            )
            if not has_time_values:
                continue

            if candidate_date.day <= 15:
                period_start = date(candidate_date.year, candidate_date.month, 1)
                period_end = date(candidate_date.year, candidate_date.month, 15)
            else:
                last_day = calendar.monthrange(candidate_date.year, candidate_date.month)[1]
                period_start = date(candidate_date.year, candidate_date.month, 16)
                period_end = date(candidate_date.year, candidate_date.month, last_day)
            detailed_periods.add((staff.pk, period_start, period_end))

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

                # PRIORITY 1: Import MONTHLY summary records only when that same half has no detailed time data.
                if str(record.get('Summary', '')).upper() == 'MONTHLY':
                    period_start = self.parse_date_value(record.get('Report Start'))
                    period_end = self.parse_date_value(record.get('Report End'))
                    if not period_start or not period_end:
                        errors += 1
                        continue
                    if (staff.pk, period_start, period_end) in detailed_periods:
                        continue
                    existing_summary = MonthlyAttendanceSummary.objects.filter(
                        staff=staff,
                        period_start__year=period_start.year,
                        period_start__month=period_start.month,
                    ).order_by('-period_end').first()

                    if existing_summary:
                        summary = existing_summary
                        created = False
                    else:
                        summary = MonthlyAttendanceSummary(staff=staff, period_start=period_start, period_end=period_end)
                        created = True

                    summary.period_start = period_start
                    summary.period_end = period_end
                    summary.working_days = int(self._coerce_decimal(self._get_first_matching_value(record, {
                        'working days', 'work days', 'scheduled days',
                    })))
                    summary.attendance_days = int(self._coerce_decimal(self._get_first_matching_value(record, {
                        'attendance days', 'attended days', 'days present', 'present days',
                    })))
                    summary.absence_days = int(self._coerce_decimal(self._get_first_matching_value(record, {
                        'absences days', 'absence days', 'absent days', 'days absent',
                    })))
                    summary.late_days = int(self._coerce_decimal(self._get_first_matching_value(record, {'late num', 'late number'})))
                    summary.overtime_hours = self._coerce_decimal(self._get_first_matching_value(record, {
                        'overtime hours', 'overtime hour', 'ot hours', 'ot hour',
                    }))
                    summary.sick_hours = self._coerce_decimal(self._get_first_matching_value(record, {'sick hours'}))
                    summary.leave_hours = self._coerce_decimal(self._get_first_matching_value(record, {'leave hours'}))
                    summary.daily_salary = Decimal('0')
                    summary.overtime_pay = Decimal('0')
                    summary.charges = Decimal('0')
                    summary.source_filename = source_filename
                    summary.uploaded_by = uploaded_by
                    summary.review_status = MonthlyAttendanceSummary.ReviewStatus.IMPORTED
                    summary.approved_by = None
                    summary.approved_at = None
                    summary.save()

                    self.import_results.append({'status': 'updated' if not created else 'imported', 'staff': staff.full_name, 'biometric_id': staff.biometric_id})
                    imported += 1
                    matched += 1
                    continue

                # PRIORITY 2: Import daily attendance with 4-punch validation
                attendance_date = self.parse_date_value(self._get_first_matching_value(
                    record, {'date', 'attendance date', 'work date'}
                ))
                if not attendance_date:
                    errors += 1
                    continue
                
                # Extract 4-punch times (STRICT: ALL REQUIRED for attendance)
                morning_in = self.parse_time_value(self._get_first_matching_value(record, {
                    'morning in', 'morning time in', 'am in', 'morning_in'
                }))
                morning_out = self.parse_time_value(self._get_first_matching_value(record, {
                    'morning out', 'morning time out', 'am out', 'morning_out'
                }))
                afternoon_in = self.parse_time_value(self._get_first_matching_value(record, {
                    'afternoon in', 'afternoon time in', 'pm in', 'after noon in', 'afternoon_in'
                }))
                afternoon_out = self.parse_time_value(self._get_first_matching_value(record, {
                    'afternoon out', 'afternoon time out', 'pm out', 'after noon out', 'afternoon_out'
                }))
                overtime_in = self.parse_time_value(self._get_first_matching_value(record, {
                    'overtime in', 'overtime time in', 'ot in', 'ot_in'
                }))
                overtime_out = self.parse_time_value(self._get_first_matching_value(record, {
                    'overtime out', 'overtime time out', 'ot out', 'ot_out'
                }))

                generic_check_in = self.parse_time_value(self._get_first_matching_value(record, {
                    'time in', 'check in', 'clock in', 'in time', 'timein', 'login'
                }))
                generic_check_out = self.parse_time_value(self._get_first_matching_value(record, {
                    'time out', 'check out', 'clock out', 'out time', 'timeout', 'logout'
                }))

                # 4-PUNCH RULE: ALL FOUR MUST BE PRESENT for attendance.
                # Summary-style single pair records are still valid when they represent a full-day attendance entry.
                has_all_four_punches = bool(morning_in and morning_out and afternoon_in and afternoon_out)
                has_single_day_pair = bool(generic_check_in and generic_check_out)

                if has_all_four_punches:
                    check_in = morning_in
                    check_out = afternoon_out
                    total_minutes = 0
                    try:
                        m_in = datetime.strptime(morning_in.strftime('%H:%M'), '%H:%M').time()
                        m_out = datetime.strptime(morning_out.strftime('%H:%M'), '%H:%M').time()
                        a_in = datetime.strptime(afternoon_in.strftime('%H:%M'), '%H:%M').time()
                        a_out = datetime.strptime(afternoon_out.strftime('%H:%M'), '%H:%M').time()

                        total_minutes += int((datetime.combine(date.today(), m_out) -
                                             datetime.combine(date.today(), m_in)).total_seconds() // 60)
                        total_minutes += int((datetime.combine(date.today(), a_out) -
                                             datetime.combine(date.today(), a_in)).total_seconds() // 60)
                    except (ValueError, TypeError):
                        total_minutes = 0
                    is_present = True
                    status = 'PRESENT'
                elif has_single_day_pair:
                    check_in = generic_check_in
                    check_out = generic_check_out
                    total_minutes = 0
                    try:
                        total_minutes = int((datetime.combine(date.today(), generic_check_out) -
                                             datetime.combine(date.today(), generic_check_in)).total_seconds() // 60)
                    except (TypeError, ValueError):
                        total_minutes = 0
                    is_present = True
                    status = 'PRESENT'
                else:
                    # Missing any punch → ABSENT
                    check_in = None
                    check_out = None
                    total_minutes = 0
                    is_present = False
                    status = 'ABSENT'

                daily, _ = DailyAttendance.objects.get_or_create(staff=staff, attendance_date=attendance_date)
                
                # Populate all fields
                daily.morning_in = morning_in
                daily.morning_out = morning_out
                daily.afternoon_in = afternoon_in
                daily.afternoon_out = afternoon_out
                daily.ot_in = overtime_in
                daily.ot_out = overtime_out
                daily.ot_hours_calculated = Decimal('0')
                if overtime_in and overtime_out:
                    overtime_minutes = int((datetime.combine(date.today(), overtime_out) - datetime.combine(date.today(), overtime_in)).total_seconds() // 60)
                    if overtime_minutes > 0:
                        daily.ot_hours_calculated = Decimal(overtime_minutes) / Decimal('60')
                daily.check_in = check_in
                daily.check_out = check_out
                daily.is_present = is_present
                daily.status = status
                daily.total_work_minutes = total_minutes
                daily.four_punch_complete = bool(
                    morning_in and morning_out and afternoon_in and afternoon_out
                )
                daily.punch_validation_status = 'PASS' if daily.four_punch_complete else 'FAIL'
                daily.punch_validation_error = '' if daily.four_punch_complete else 'All four morning and afternoon punches are required.'
                daily.late_minutes = int(self._coerce_decimal(self._get_first_matching_value(record, {
                    'late minutes', 'minutes late'
                }, fallback_aliases={'late min'})))
                daily.overtime_minutes = int(self._coerce_decimal(self._get_first_matching_value(record, {
                    'overtime minutes', 'ot minutes', 'overtime min', 'ot min'
                }, fallback_aliases={'ot minutes'})))
                daily.is_approved = True
                daily.save()
                imported += 1
                matched += 1
            except Exception as exc:
                errors += 1
                logger.exception('Error importing attendance summary record: %s', exc)
        return imported, matched, errors
    
    @staticmethod
    def populate_granular_punch_data(daily_record: DailyAttendance, import_record: dict) -> None:
        """
        Populate granular 4-punch fields (morning_in/out, afternoon_in/out) from import record.
        
        Args:
            daily_record: DailyAttendance model instance to populate
            import_record: Dictionary from imported file
        """
        # Extract granular punch data using validators
        morning_in = FourPunchValidator.find_column_in_record(
            import_record, FourPunchValidator.MORNING_IN_ALIASES
        )
        morning_out = FourPunchValidator.find_column_in_record(
            import_record, FourPunchValidator.MORNING_OUT_ALIASES
        )
        afternoon_in = FourPunchValidator.find_column_in_record(
            import_record, FourPunchValidator.AFTERNOON_IN_ALIASES
        )
        afternoon_out = FourPunchValidator.find_column_in_record(
            import_record, FourPunchValidator.AFTERNOON_OUT_ALIASES
        )
        
        # Parse times and populate fields
        daily_record.morning_in = FourPunchValidator.parse_time_value(morning_in)
        daily_record.morning_out = FourPunchValidator.parse_time_value(morning_out)
        daily_record.afternoon_in = FourPunchValidator.parse_time_value(afternoon_in)
        daily_record.afternoon_out = FourPunchValidator.parse_time_value(afternoon_out)
        
        # Extract OT data
        ot_in = OvertimeCalculator.find_column_in_record(
            import_record, OvertimeCalculator.OT_IN_ALIASES
        )
        ot_out = OvertimeCalculator.find_column_in_record(
            import_record, OvertimeCalculator.OT_OUT_ALIASES
        )
        
        daily_record.ot_in = FourPunchValidator.parse_time_value(ot_in)
        daily_record.ot_out = FourPunchValidator.parse_time_value(ot_out)
        
        # Calculate OT hours if both timestamps present
        if daily_record.ot_in and daily_record.ot_out:
            ot_in_dt = datetime.combine(date.today(), daily_record.ot_in)
            ot_out_dt = datetime.combine(date.today(), daily_record.ot_out)
            delta = ot_out_dt - ot_in_dt
            if delta.total_seconds() > 0:
                daily_record.ot_hours_calculated = Decimal(str(delta.total_seconds() / 3600))
        
        # Validate 4-punch rule
        validation_result = FourPunchValidator.validate_daily_record(import_record)
        daily_record.four_punch_complete = validation_result.is_valid
        daily_record.punch_validation_status = 'PASS' if validation_result.is_valid else 'FAIL'
        if not validation_result.is_valid:
            daily_record.punch_validation_error = '; '.join(validation_result.errors)
        
        # Mark as ABSENT if 4-punch validation failed
        if not daily_record.four_punch_complete:
            daily_record.is_present = False
            daily_record.status = 'ABSENT'
    
    @staticmethod
    def calculate_monthly_required_working_days(
        year: int,
        month: int,
        period_type: str = 'SEMI_FIRST',
        default_rest_days: int = 4,
    ) -> tuple:
        """
        Calculate required working days for a monthly period.
        
        Returns:
            Tuple of (required_days, first_half_required, second_half_required)
        """
        first_half, second_half = WorkingDaysCalculator.calculate_working_days_for_full_month(
            year, month, default_rest_days
        )
        
        if period_type == 'SEMI_FIRST':
            required_days = first_half
        elif period_type == 'SEMI_SECOND':
            required_days = second_half
        else:
            required_days = first_half + second_half
        
        return required_days, first_half, second_half
    
    @staticmethod
    def update_monthly_summary_with_calculations(
        summary: MonthlyAttendanceSummary,
        year: int,
        month: int,
        period_type: str = 'SEMI_FIRST',
        default_rest_days: int = 4,
    ) -> None:
        """
        Update MonthlyAttendanceSummary with calculated metrics.
        
        Populates:
        - required_working_days
        - required_working_days_first_half
        - required_working_days_second_half
        - four_punch_validation_status
        - four_punch_violations_count
        """
        # Calculate required working days
        required_days, first_half_req, second_half_req = (
            AttendanceImportService.calculate_monthly_required_working_days(
                year, month, period_type, default_rest_days
            )
        )
        
        summary.required_working_days = required_days
        summary.required_working_days_first_half = first_half_req
        summary.required_working_days_second_half = second_half_req
        
        # Get all daily records for this period
        daily_records = DailyAttendance.objects.filter(
            staff=summary.staff,
            attendance_date__range=[summary.period_start, summary.period_end],
        )
        
        # Analyze 4-punch validation
        total_days = daily_records.count()
        passed_days = daily_records.filter(four_punch_complete=True).count()
        failed_days = daily_records.filter(four_punch_complete=False).count()
        
        summary.four_punch_violations_count = failed_days
        
        if total_days == 0:
            summary.four_punch_validation_status = 'PENDING'
        elif failed_days == 0:
            summary.four_punch_validation_status = 'PASS'
        elif passed_days == 0:
            summary.four_punch_validation_status = 'FAIL'
        else:
            summary.four_punch_validation_status = 'PARTIAL'
        
        # Collect violation details
        violations = []
        for record in daily_records.filter(four_punch_complete=False):
            violations.append({
                'date': str(record.attendance_date),
                'error': record.punch_validation_error,
            })
        summary.four_punch_violations = violations
        
        summary.save()


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
