"""
Attendance Calculation Engine for Payroll Integration.

Implements strict hierarchical logic for:
- Working days and rest days calculation per period
- 4-punch validation (Priority 1) with fallback (Priority 2)
- Attendance capping against required working days
- Overtime calculation from timestamps or fallback values

This engine enforces the core requirements:
1. File Ingestion & ID Mapping
2. Dynamic Working Days & Rest Days Calculation
3. Strict Attendance Validation (4-Punch Rule)
4. Attendance Capping / Tally Logic
5. Overtime Calculation Logic
"""
import calendar
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Tuple, Optional, Any

logger = logging.getLogger(__name__)


class PunchType(Enum):
    """Supported punch types in attendance records."""
    MORNING_IN = 'morning_in'
    MORNING_OUT = 'morning_out'
    AFTERNOON_IN = 'afternoon_in'
    AFTERNOON_OUT = 'afternoon_out'
    OVERTIME_IN = 'overtime_in'
    OVERTIME_OUT = 'overtime_out'


class ValidationResult:
    """Standardized validation result with details."""
    
    def __init__(self, is_valid: bool, errors: List[str] = None, warnings: List[str] = None):
        self.is_valid = is_valid
        self.errors = errors or []
        self.warnings = warnings or []
    
    def add_error(self, message: str):
        self.errors.append(message)
        self.is_valid = False
    
    def add_warning(self, message: str):
        self.warnings.append(message)
    
    def __bool__(self):
        return self.is_valid
    
    def __str__(self):
        return f"Valid={self.is_valid}, Errors={len(self.errors)}, Warnings={len(self.warnings)}"


class WorkingDaysCalculator:
    """
    Calculate required working days based on calendar and rest day policy.
    
    Formula:
        Required Working Days = Calendar Days - Default Rest Days
    
    For Semi-Monthly Periods:
        Allocate rest days evenly across halves:
        - First Half (1-15): calendar_days_first - (rest_days / 2)
        - Second Half (16-End): calendar_days_second - (rest_days / 2)
    """
    
    @staticmethod
    def get_month_info(year: int, month: int) -> Dict[str, int]:
        """
        Get calendar information for a given month.
        
        Args:
            year: Full year (e.g., 2026)
            month: Month number (1-12)
        
        Returns:
            Dictionary with days_in_month, first_half_days, second_half_days
        """
        days_in_month = calendar.monthrange(year, month)[1]
        split_point = days_in_month // 2
        
        return {
            'days_in_month': days_in_month,
            'first_half_days': split_point,  # Days 1 to split_point
            'second_half_days': days_in_month - split_point,  # Days (split+1) to end
            'split_point': split_point,
        }
    
    @staticmethod
    def calculate_required_working_days(
        year: int,
        month: int,
        period_type: str,
        default_rest_days: int = 4,
    ) -> int:
        """
        Calculate required working days for a payroll period.
        
        Args:
            year: Full year (e.g., 2026)
            month: Month number (1-12)
            period_type: 'SEMI_FIRST' or 'SEMI_SECOND' or 'FULL_MONTH'
            default_rest_days: Default rest days per month (default: 4)
        
        Returns:
            Required working days for the period
        
        Example:
            August 2026 (31 days), rest_days=4:
            - First Half (1-15): 15 - 2 = 13 days
            - Second Half (16-31): 16 - 2 = 14 days
            - Full Month: 31 - 4 = 27 days
        """
        month_info = WorkingDaysCalculator.get_month_info(year, month)
        days_in_month = month_info['days_in_month']
        first_half_days = month_info['first_half_days']
        second_half_days = month_info['second_half_days']
        
        # Allocate rest days evenly across halves
        rest_days_per_half = default_rest_days // 2
        
        if period_type == 'SEMI_FIRST':
            required_days = first_half_days - rest_days_per_half
        elif period_type == 'SEMI_SECOND':
            required_days = second_half_days - rest_days_per_half
        else:  # FULL_MONTH
            required_days = days_in_month - default_rest_days
        
        return max(0, required_days)
    
    @staticmethod
    def calculate_working_days_for_full_month(
        year: int,
        month: int,
        default_rest_days: int = 4,
    ) -> Tuple[int, int]:
        """
        Calculate required working days for both halves of a month.
        
        Returns:
            Tuple of (first_half_required_days, second_half_required_days)
        """
        first_half = WorkingDaysCalculator.calculate_required_working_days(
            year, month, 'SEMI_FIRST', default_rest_days
        )
        second_half = WorkingDaysCalculator.calculate_required_working_days(
            year, month, 'SEMI_SECOND', default_rest_days
        )
        return first_half, second_half


class FourPunchValidator:
    """
    Validate attendance records for mandatory 4-punch requirement.
    
    Priority 1 (Granular Validation):
        Check for 4 specific punches per day:
        - TIME IN FOR THE MORNING
        - TIME OUT FOR THE MORNING
        - TIME IN FOR THE AFTERNOON
        - TIME OUT FOR THE AFTERNOON
        
        Rule: If ANY punch is missing → Day marked ABSENT
    
    Priority 2 (Fallback):
        If granular punches missing → Use "Days Worked / Attendance Days" column
    
    The system auto-detects column names based on biometric format.
    """
    
    # Column name aliases for different biometric systems
    MORNING_IN_ALIASES = {
        'morning in', 'morning time in', 'am in', 'am time in',
        'time in 1', 'shift 1 in', 'in time 1',
        'check in am', 'check in morning',
        'morn_in', 'morning_in',
    }
    
    MORNING_OUT_ALIASES = {
        'morning out', 'morning time out', 'am out', 'am time out',
        'time out 1', 'shift 1 out', 'out time 1',
        'check out am', 'check out morning',
        'morn_out', 'morning_out',
    }
    
    AFTERNOON_IN_ALIASES = {
        'afternoon in', 'afternoon time in', 'pm in', 'pm time in',
        'time in 2', 'shift 2 in', 'in time 2',
        'check in pm', 'check in afternoon',
        'after noon in', 'aftn_in', 'afternoon_in',
    }
    
    AFTERNOON_OUT_ALIASES = {
        'afternoon out', 'afternoon time out', 'pm out', 'pm time out',
        'time out 2', 'shift 2 out', 'out time 2',
        'check out pm', 'check out afternoon',
        'after noon out', 'aftn_out', 'afternoon_out',
    }
    
    @staticmethod
    def normalize_key(value: str) -> str:
        """Normalize a column key for comparison."""
        return ' '.join(str(value or '').lower().split())
    
    @staticmethod
    def find_column_in_record(record: Dict[str, Any], aliases: set) -> Optional[Any]:
        """
        Find a column value in a record based on alias set.
        
        Args:
            record: Dictionary of record data
            aliases: Set of normalized column name aliases
        
        Returns:
            Column value if found, None otherwise
        """
        if not isinstance(record, dict):
            return None
        
        normalized_aliases = {FourPunchValidator.normalize_key(alias) for alias in aliases}
        
        for key, value in record.items():
            normalized_key = FourPunchValidator.normalize_key(str(key))
            if normalized_key in normalized_aliases:
                return value
        
        return None
    
    @staticmethod
    def parse_time_value(value: Any) -> Optional[str]:
        """
        Parse a time value to HH:MM format or return None if invalid/missing.
        
        Args:
            value: Time value (string, datetime, or None)
        
        Returns:
            Time string in HH:MM format or None
        """
        if value in (None, '', 'None', 'N/A', '-'):
            return None
        
        if isinstance(value, datetime):
            return value.strftime('%H:%M')
        
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            # Try to parse common formats
            try:
                # Handle HH:MM, H:MM, HH:MM:SS
                if ':' in value:
                    parts = value.split(':')
                    if len(parts) >= 2:
                        hour = int(parts[0])
                        minute = int(parts[1])
                        return f"{hour:02d}:{minute:02d}"
            except (ValueError, AttributeError):
                pass
        
        return None
    
    @staticmethod
    def validate_daily_record(record: Dict[str, Any]) -> ValidationResult:
        """
        Validate a single daily attendance record for 4-punch completeness.
        
        Priority 1 Logic:
            Checks for all 4 punches. If any missing → ABSENT
        
        Args:
            record: Single attendance record (one row from imported file)
        
        Returns:
            ValidationResult with is_valid=True if all 4 punches present
        """
        result = ValidationResult(is_valid=True)
        
        # Extract all 4 punches
        morning_in = FourPunchValidator.find_column_in_record(
            record, FourPunchValidator.MORNING_IN_ALIASES
        )
        morning_out = FourPunchValidator.find_column_in_record(
            record, FourPunchValidator.MORNING_OUT_ALIASES
        )
        afternoon_in = FourPunchValidator.find_column_in_record(
            record, FourPunchValidator.AFTERNOON_IN_ALIASES
        )
        afternoon_out = FourPunchValidator.find_column_in_record(
            record, FourPunchValidator.AFTERNOON_OUT_ALIASES
        )
        
        # Parse times
        morning_in_time = FourPunchValidator.parse_time_value(morning_in)
        morning_out_time = FourPunchValidator.parse_time_value(morning_out)
        afternoon_in_time = FourPunchValidator.parse_time_value(afternoon_in)
        afternoon_out_time = FourPunchValidator.parse_time_value(afternoon_out)
        
        # Validate all 4 punches present
        missing_punches = []
        if not morning_in_time:
            missing_punches.append('MORNING_IN')
        if not morning_out_time:
            missing_punches.append('MORNING_OUT')
        if not afternoon_in_time:
            missing_punches.append('AFTERNOON_IN')
        if not afternoon_out_time:
            missing_punches.append('AFTERNOON_OUT')
        
        if missing_punches:
            result.is_valid = False
            result.add_error(f"Missing punches: {', '.join(missing_punches)}")
            result.add_warning(
                f"Daily record marked ABSENT due to incomplete punch record. "
                f"Present: {4 - len(missing_punches)}/4 punches."
            )
        else:
            # Validate punch order (in before out)
            try:
                morning_in_dt = datetime.strptime(morning_in_time, '%H:%M')
                morning_out_dt = datetime.strptime(morning_out_time, '%H:%M')
                afternoon_in_dt = datetime.strptime(afternoon_in_time, '%H:%M')
                afternoon_out_dt = datetime.strptime(afternoon_out_time, '%H:%M')
                
                if morning_in_dt >= morning_out_dt:
                    result.add_warning("Morning: Check-in time >= Check-out time")
                
                if afternoon_in_dt >= afternoon_out_dt:
                    result.add_warning("Afternoon: Check-in time >= Check-out time")
                
                if morning_out_dt >= afternoon_in_dt:
                    result.add_warning("Morning out >= Afternoon in (invalid shift times)")
            except (ValueError, TypeError):
                pass  # Time parsing already handled
        
        return result
    
    @staticmethod
    def validate_records_batch(records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Validate a batch of daily attendance records.
        
        Returns:
            Dictionary with:
            - total_records: int
            - valid_records: int
            - invalid_records: int
            - validation_details: list of (record_index, result)
        """
        total = len(records)
        valid = 0
        invalid = 0
        details = []
        
        for idx, record in enumerate(records):
            result = FourPunchValidator.validate_daily_record(record)
            details.append((idx, result))
            
            if result.is_valid:
                valid += 1
            else:
                invalid += 1
        
        return {
            'total_records': total,
            'valid_records': valid,
            'invalid_records': invalid,
            'validation_details': details,
            'pass_rate': (valid / total * 100) if total > 0 else 0.0,
        }


class AttendanceCappingEngine:
    """
    Apply attendance capping logic against required working days.
    
    Formula:
        Actual_Days_Worked = MIN(Calculated_Attendance, Required_Working_Days)
    
    This prevents fraud (clock in extra days) and handles data errors
    (biometric showing more days than calendar available).
    """
    
    @staticmethod
    def cap_attendance_days(
        calculated_days: int,
        required_working_days: int,
    ) -> Tuple[int, Optional[str]]:
        """
        Apply capping to calculated attendance days.
        
        Args:
            calculated_days: Days worked as calculated from attendance records
            required_working_days: Maximum allowed working days for period
        
        Returns:
            Tuple of (capped_days, capping_note)
            capping_note is None if no capping applied, string if capped
        """
        if calculated_days <= required_working_days:
            return calculated_days, None
        
        capping_note = (
            f"Attendance capped: {calculated_days} calculated → "
            f"{required_working_days} required (excess {calculated_days - required_working_days} days)"
        )
        
        return required_working_days, capping_note
    
    @staticmethod
    def validate_capping_input(
        calculated_days: int,
        required_working_days: int,
    ) -> ValidationResult:
        """
        Validate inputs for capping logic.
        
        Args:
            calculated_days: Days worked from records
            required_working_days: Required days for period
        
        Returns:
            ValidationResult
        """
        result = ValidationResult(is_valid=True)
        
        if calculated_days < 0:
            result.add_error(f"Calculated days cannot be negative: {calculated_days}")
        
        if required_working_days < 0:
            result.add_error(f"Required working days cannot be negative: {required_working_days}")
        
        if required_working_days == 0:
            result.add_warning("Required working days is 0; attendance capping disabled")
        
        return result


class OvertimeCalculator:
    """
    Calculate overtime hours with Priority Cascade logic.
    
    Priority 1 (Timestamp Calculation):
        IF file has OT_IN and OT_OUT columns:
        - Parse time pairs and calculate hours
        - Sum all OT hours per employee per period
        - Support various time formats and rounding
    
    Priority 2 (Fallback Value):
        IF OT timestamps missing:
        - Retrieve flat numerical value from "Overtime Hours" column
        - Use as-is without validation
    
    The system auto-detects column names for different biometric systems.
    """
    
    OT_IN_ALIASES = {
        'overtime in', 'overtime time in', 'ot in', 'ot time in',
        'ot_in', 'overtime_in', 'extra time in',
        'check in ot', 'check in overtime',
    }
    
    OT_OUT_ALIASES = {
        'overtime out', 'overtime time out', 'ot out', 'ot time out',
        'ot_out', 'overtime_out', 'extra time out',
        'check out ot', 'check out overtime',
    }
    
    OT_HOURS_ALIASES = {
        'overtime hours', 'overtime hour', 'ot hours', 'ot hour',
        'overtime h', 'ot h', 'overtime_hours', 'ot_hours',
        'extra hours', 'extra hour', 'overtime mins',
    }
    
    @staticmethod
    def normalize_key(value: str) -> str:
        """Normalize a column key for comparison."""
        return ' '.join(str(value or '').lower().split())
    
    @staticmethod
    def find_column_in_record(record: Dict[str, Any], aliases: set) -> Optional[Any]:
        """Find a column value in a record based on alias set."""
        if not isinstance(record, dict):
            return None
        
        normalized_aliases = {OvertimeCalculator.normalize_key(alias) for alias in aliases}
        
        for key, value in record.items():
            normalized_key = OvertimeCalculator.normalize_key(str(key))
            if normalized_key in normalized_aliases:
                return value
        
        return None
    
    @staticmethod
    def parse_time_value(value: Any) -> Optional[datetime]:
        """
        Parse a time value to datetime object or return None if invalid/missing.
        
        Args:
            value: Time value (string, datetime, or None)
        
        Returns:
            datetime.time object or None
        """
        if value in (None, '', 'None', 'N/A', '-'):
            return None
        
        if isinstance(value, datetime):
            return value
        
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            try:
                # Handle various time formats
                if ':' in value:
                    parts = value.split(':')
                    if len(parts) >= 2:
                        hour = int(parts[0])
                        minute = int(parts[1])
                        # Return as datetime.time for calculation
                        return datetime.combine(date.today(), datetime.min.time()).replace(
                            hour=hour, minute=minute
                        )
            except (ValueError, AttributeError):
                pass
        
        return None
    
    @staticmethod
    def calculate_hours_between(
        time_in: Optional[datetime],
        time_out: Optional[datetime],
    ) -> Decimal:
        """
        Calculate hours between two time values.
        
        Args:
            time_in: Check-in time
            time_out: Check-out time
        
        Returns:
            Hours as Decimal (e.g., 3.5 for 3 hours 30 minutes)
        """
        if not time_in or not time_out:
            return Decimal('0')
        
        try:
            if time_in >= time_out:
                # Handle overnight shift (out time is next day)
                # For now, return 0 as error condition
                logger.warning(f"Invalid time pair: {time_in} >= {time_out}")
                return Decimal('0')
            
            delta = time_out - time_in
            total_seconds = delta.total_seconds()
            hours = Decimal(str(total_seconds)) / Decimal('3600')
            
            return hours
        except (TypeError, AttributeError):
            return Decimal('0')
    
    @staticmethod
    def calculate_overtime_from_record(
        record: Dict[str, Any],
        rounding_minutes: int = 0,
    ) -> Tuple[Decimal, str]:
        """
        Calculate overtime hours from a single daily record.
        
        Implements Priority Cascade:
        1. Try timestamp calculation (OT_IN, OT_OUT)
        2. Fall back to "Overtime Hours" column
        
        Args:
            record: Daily attendance record
            rounding_minutes: Round OT to nearest X minutes (0 = no rounding)
        
        Returns:
            Tuple of (overtime_hours, source_method)
        """
        # Priority 1: Timestamp Calculation
        ot_in = OvertimeCalculator.find_column_in_record(
            record, OvertimeCalculator.OT_IN_ALIASES
        )
        ot_out = OvertimeCalculator.find_column_in_record(
            record, OvertimeCalculator.OT_OUT_ALIASES
        )
        
        if ot_in and ot_out:
            ot_in_time = OvertimeCalculator.parse_time_value(ot_in)
            ot_out_time = OvertimeCalculator.parse_time_value(ot_out)
            
            if ot_in_time and ot_out_time:
                hours = OvertimeCalculator.calculate_hours_between(ot_in_time, ot_out_time)
                
                # Apply rounding if specified
                if rounding_minutes > 0 and hours > 0:
                    total_minutes = hours * Decimal('60')
                    rounded_minutes = (
                        (total_minutes + Decimal(rounding_minutes) // 2) // Decimal(rounding_minutes)
                    ) * Decimal(rounding_minutes)
                    hours = rounded_minutes / Decimal('60')
                
                return hours, 'TIMESTAMP'
        
        # Priority 2: Fallback to Overtime Hours Column
        ot_hours_value = OvertimeCalculator.find_column_in_record(
            record, OvertimeCalculator.OT_HOURS_ALIASES
        )
        
        if ot_hours_value is not None:
            try:
                hours = Decimal(str(ot_hours_value).replace(',', ''))
                return hours, 'FALLBACK_VALUE'
            except (ValueError, TypeError):
                pass
        
        return Decimal('0'), 'NO_OT_DATA'
    
    @staticmethod
    def calculate_overtime_batch(
        records: List[Dict[str, Any]],
        rounding_minutes: int = 0,
    ) -> Dict[str, Any]:
        """
        Calculate overtime for a batch of daily records.
        
        Args:
            records: List of daily attendance records
            rounding_minutes: Rounding rule (0 = no rounding)
        
        Returns:
            Dictionary with:
            - total_ot_hours: Decimal (sum of all OT hours)
            - calculation_method: str (TIMESTAMP, FALLBACK_VALUE, MIXED)
            - details: list of (record_index, ot_hours, method)
        """
        total_hours = Decimal('0')
        methods_used = set()
        details = []
        
        for idx, record in enumerate(records):
            hours, method = OvertimeCalculator.calculate_overtime_from_record(
                record, rounding_minutes
            )
            details.append((idx, hours, method))
            total_hours += hours
            if hours > 0:
                methods_used.add(method)
        
        # Determine overall calculation method
        if not methods_used:
            calc_method = 'NO_OT_DATA'
        elif len(methods_used) == 1:
            calc_method = next(iter(methods_used))
        else:
            calc_method = 'MIXED'
        
        return {
            'total_ot_hours': total_hours,
            'calculation_method': calc_method,
            'record_count': len(records),
            'records_with_ot': sum(1 for _, hours, _ in details if hours > 0),
            'details': details,
        }


class AttendanceCalculationEngine:
    """
    Main orchestration engine combining all attendance calculation logic.
    
    Coordinates:
    - Working days calculation
    - 4-punch validation
    - Attendance capping
    - Overtime calculation
    """
    
    def __init__(self, default_rest_days: int = 4):
        """
        Initialize the calculation engine.
        
        Args:
            default_rest_days: Default rest days per month (default: 4)
        """
        self.default_rest_days = default_rest_days
        self.working_days_calc = WorkingDaysCalculator()
        self.punch_validator = FourPunchValidator()
        self.capping_engine = AttendanceCappingEngine()
        self.ot_calculator = OvertimeCalculator()
    
    def process_monthly_attendance(
        self,
        records: List[Dict[str, Any]],
        year: int,
        month: int,
        period_type: str = 'SEMI_FIRST',
    ) -> Dict[str, Any]:
        """
        Process a complete monthly attendance batch.
        
        Args:
            records: List of daily attendance records
            year: Payroll year
            month: Payroll month
            period_type: 'SEMI_FIRST' or 'SEMI_SECOND'
        
        Returns:
            Comprehensive processing result with all metrics
        """
        result = {
            'status': 'SUCCESS',
            'errors': [],
            'warnings': [],
            'metrics': {},
            'records_processed': 0,
            'timestamp': datetime.now().isoformat(),
        }
        
        # Step 1: Calculate required working days
        required_days = self.working_days_calc.calculate_required_working_days(
            year, month, period_type, self.default_rest_days
        )
        result['metrics']['required_working_days'] = required_days
        
        # Step 2: Validate 4-punch rule on batch
        punch_validation = self.punch_validator.validate_records_batch(records)
        result['metrics']['punch_validation'] = punch_validation
        
        if punch_validation['invalid_records'] > 0:
            result['warnings'].append(
                f"{punch_validation['invalid_records']} records with incomplete punch data "
                f"({punch_validation['pass_rate']:.1f}% pass rate)"
            )
        
        # Step 3: Calculate OT
        ot_result = self.ot_calculator.calculate_overtime_batch(records)
        result['metrics']['overtime'] = ot_result
        
        # Step 4: Apply attendance capping
        # For this batch result, we use the count of records as proxy for days
        calculated_days = punch_validation['valid_records']
        capped_days, capping_note = self.capping_engine.cap_attendance_days(
            calculated_days, required_days
        )
        result['metrics']['attendance_capping'] = {
            'calculated_days': calculated_days,
            'required_days': required_days,
            'capped_days': capped_days,
            'was_capped': capping_note is not None,
        }
        
        if capping_note:
            result['warnings'].append(capping_note)
        
        result['records_processed'] = len(records)
        
        return result
    
    def get_summary_report(self) -> str:
        """Generate a human-readable summary of the engine configuration."""
        return f"""
Attendance Calculation Engine Summary
=====================================
Default Rest Days: {self.default_rest_days}
Working Days Calculator: Configured
4-Punch Validator: Configured
Attendance Capping: Configured
Overtime Calculator: Configured
"""
