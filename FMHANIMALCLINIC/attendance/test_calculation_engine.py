"""
Comprehensive Test Suite for Attendance Calculation Engine.

Tests cover:
1. Working Days & Rest Days Calculation
2. 4-Punch Validation (Priority 1 & 2)
3. Attendance Capping Logic
4. Overtime Calculation with Priority Cascade
"""
import unittest
from datetime import date, datetime, time
from decimal import Decimal

from attendance.calculation_engine import (
    WorkingDaysCalculator,
    FourPunchValidator,
    AttendanceCappingEngine,
    OvertimeCalculator,
    AttendanceCalculationEngine,
    ValidationResult,
)


class TestWorkingDaysCalculator(unittest.TestCase):
    """Test working days calculation engine."""
    
    def test_get_month_info_31_days(self):
        """Test month info calculation for 31-day month (August 2026)."""
        month_info = WorkingDaysCalculator.get_month_info(2026, 8)
        
        self.assertEqual(month_info['days_in_month'], 31)
        self.assertEqual(month_info['first_half_days'], 15)
        self.assertEqual(month_info['second_half_days'], 16)
        self.assertEqual(month_info['split_point'], 15)
    
    def test_get_month_info_30_days(self):
        """Test month info calculation for 30-day month."""
        month_info = WorkingDaysCalculator.get_month_info(2026, 9)  # September
        
        self.assertEqual(month_info['days_in_month'], 30)
        self.assertEqual(month_info['first_half_days'], 15)
        self.assertEqual(month_info['second_half_days'], 15)
    
    def test_get_month_info_28_days(self):
        """Test month info calculation for 28-day month (February non-leap)."""
        month_info = WorkingDaysCalculator.get_month_info(2023, 2)  # Feb 2023
        
        self.assertEqual(month_info['days_in_month'], 28)
        self.assertEqual(month_info['first_half_days'], 14)
        self.assertEqual(month_info['second_half_days'], 14)
    
    def test_calculate_required_working_days_semi_first_31_day_month(self):
        """
        Test required working days for First Half of 31-day month.
        August 2026: 31 - 4 = 27 total
        First Half (1-15): 15 - 2 = 13 required
        """
        required = WorkingDaysCalculator.calculate_required_working_days(
            2026, 8, 'SEMI_FIRST', default_rest_days=4
        )
        
        self.assertEqual(required, 13)
    
    def test_calculate_required_working_days_semi_second_31_day_month(self):
        """
        Test required working days for Second Half of 31-day month.
        August 2026: 31 - 4 = 27 total
        Second Half (16-31): 16 - 2 = 14 required
        """
        required = WorkingDaysCalculator.calculate_required_working_days(
            2026, 8, 'SEMI_SECOND', default_rest_days=4
        )
        
        self.assertEqual(required, 14)
    
    def test_calculate_required_working_days_full_month(self):
        """
        Test required working days for full month.
        August 2026: 31 - 4 = 27 required
        """
        required = WorkingDaysCalculator.calculate_required_working_days(
            2026, 8, 'FULL_MONTH', default_rest_days=4
        )
        
        self.assertEqual(required, 27)


class TestFourPunchValidator(unittest.TestCase):
    """Test 4-punch validation logic."""
    
    def test_validate_daily_record_complete_4_punches(self):
        """Test validation with all 4 punches present."""
        record = {
            'Morning In': '08:00',
            'Morning Out': '12:00',
            'Afternoon In': '13:00',
            'Afternoon Out': '17:00',
        }
        
        result = FourPunchValidator.validate_daily_record(record)
        
        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.errors), 0)
    
    def test_validate_daily_record_missing_morning_out(self):
        """Test validation with missing morning out punch."""
        record = {
            'Morning In': '08:00',
            'Morning Out': None,
            'Afternoon In': '13:00',
            'Afternoon Out': '17:00',
        }
        
        result = FourPunchValidator.validate_daily_record(record)
        
        self.assertFalse(result.is_valid)
        self.assertIn('MORNING_OUT', result.errors[0])
    
    def test_validate_records_batch(self):
        """Test batch validation of multiple records."""
        records = [
            {
                'Date': '2026-08-01',
                'Morning In': '08:00',
                'Morning Out': '12:00',
                'Afternoon In': '13:00',
                'Afternoon Out': '17:00',
            },
            {
                'Date': '2026-08-02',
                'Morning In': '08:00',
                'Morning Out': None,  # Missing
                'Afternoon In': '13:00',
                'Afternoon Out': '17:00',
            },
        ]
        
        result = FourPunchValidator.validate_records_batch(records)
        
        self.assertEqual(result['total_records'], 2)
        self.assertEqual(result['valid_records'], 1)
        self.assertEqual(result['invalid_records'], 1)


class TestAttendanceCappingEngine(unittest.TestCase):
    """Test attendance capping logic."""
    
    def test_cap_attendance_days_no_capping_needed(self):
        """Test when calculated days <= required days."""
        calculated = 13
        required = 13
        
        capped, note = AttendanceCappingEngine.cap_attendance_days(calculated, required)
        
        self.assertEqual(capped, 13)
        self.assertIsNone(note)
    
    def test_cap_attendance_days_exceeds_required(self):
        """Test when calculated days > required days (capping needed)."""
        calculated = 15
        required = 13
        
        capped, note = AttendanceCappingEngine.cap_attendance_days(calculated, required)
        
        self.assertEqual(capped, 13)
        self.assertIsNotNone(note)


class TestOvertimeCalculator(unittest.TestCase):
    """Test overtime calculation engine."""
    
    def test_calculate_overtime_from_record_timestamp_priority(self):
        """Test Priority 1: OT calculation from timestamps."""
        record = {
            'OT In': '16:00',
            'OT Out': '19:00',
            'Overtime Hours': '2.0',  # Should be ignored
        }
        
        hours, method = OvertimeCalculator.calculate_overtime_from_record(record)
        
        self.assertEqual(hours, Decimal('3'))
        self.assertEqual(method, 'TIMESTAMP')
    
    def test_calculate_overtime_from_record_fallback_priority(self):
        """Test Priority 2: Fallback to Overtime Hours column."""
        record = {
            'OT In': None,
            'OT Out': None,
            'Overtime Hours': '4.5',
        }
        
        hours, method = OvertimeCalculator.calculate_overtime_from_record(record)
        
        self.assertEqual(hours, Decimal('4.5'))
        self.assertEqual(method, 'FALLBACK_VALUE')


if __name__ == '__main__':
    unittest.main()
