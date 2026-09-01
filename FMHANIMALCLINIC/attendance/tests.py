from datetime import date
import io
import zipfile

from django.apps import apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from openpyxl import Workbook

from attendance.forms import AttendanceImportForm
from attendance.models import AttendanceUpload, DailyAttendance, MonthlyAttendanceSummary
from attendance.services import AttendanceImportService
from branches.models import Branch
from employees.models import StaffMember


class AttendanceSummaryImportTests(TestCase):
  def test_attendance_exception_model_is_removed(self):
    with self.assertRaises(LookupError):
      apps.get_model('attendance', 'AttendanceException')

  def setUp(self):
    self.branch = Branch.objects.create(
      name='Main Branch',
      branch_code='MAIN',
      phone_number='09123456789',
      address='123 Test Ave',
      city='Manila',
      state='NCR',
      zip_code='1000',
    )
    self.staff = StaffMember.objects.create(
      first_name='Ana',
      last_name='Santos',
      biometric_id='BIO-001',
      position=StaffMember.Position.VETERINARIAN,
      salary=40000,
      branch=self.branch,
      is_active=True,
    )

  def test_summary_import_matches_staff_by_biometric_id(self):
        records = [{
            'Biometric ID': 'BIO-001',
            'Date': '2026-08-10',
            'Status': 'Present',
            'Time In': '08:00',
            'Time Out': '17:00',
            'Late Minutes': '0',
            'Overtime Minutes': '60',
            'Total Work Minutes': '540',
        }]

        imported, matched, errors = AttendanceImportService().import_summary_records(records)

        self.assertEqual(imported, 1)
        self.assertEqual(matched, 1)
        self.assertEqual(errors, 0)

        daily = DailyAttendance.objects.get(
            staff=self.staff,
            attendance_date=date(2026, 8, 10),
        )

        self.assertTrue(daily.is_present)
        self.assertEqual(daily.status, 'PRESENT')
        self.assertEqual(daily.check_in.hour, 8)
        self.assertEqual(daily.check_out.hour, 17)
        self.assertEqual(daily.total_work_minutes, 540)
        self.assertEqual(daily.overtime_minutes, 60)

  def test_summary_import_accepts_nonstandard_time_aliases(self):
        records = [{
            'Employee Number': 'BIO-001',
            'Date': '2026-08-11',
            'TimeIn': '08:15',
            'Timeout': '17:45',
            'OT Minutes': '45',
            'Worked Minutes': '570',
        }]

        imported, matched, errors = AttendanceImportService().import_summary_records(records)

        self.assertEqual((imported, matched, errors), (1, 1, 0))
        daily = DailyAttendance.objects.get(staff=self.staff, attendance_date=date(2026, 8, 11))
        self.assertEqual(daily.check_in.hour, 8)
        self.assertEqual(daily.check_out.hour, 17)
        self.assertEqual(daily.overtime_minutes, 45)
        self.assertEqual(daily.total_work_minutes, 570)

  def test_parse_xml_keeps_daily_morning_afternoon_rows_in_second_half_imports(self):
        xml = b'''<?xml version="1.0"?>
        <Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
            xmlns:o="urn:schemas-microsoft-com:office:office"
            xmlns:x="urn:schemas-microsoft-com:office:excel"
            xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
          <Worksheet>
            <Table>
              <Row>
                <Cell><Data ss:Type="String">Name:Carl Vincent Sanchez</Data></Cell>
                <Cell><Data ss:Type="String">ID:00001</Data></Cell>
                <Cell><Data ss:Type="String">Date:26.08.0126.08.31</Data></Cell>
              </Row>
              <Row>
                <Cell><Data ss:Type="String">Working days:31</Data></Cell>
                <Cell><Data ss:Type="String">Attendance days:1</Data></Cell>
                <Cell><Data ss:Type="String">Absences days:30</Data></Cell>
              </Row>
              <Row>
                <Cell><Data ss:Type="String">Date</Data></Cell>
                <Cell><Data ss:Type="String">Week</Data></Cell>
                <Cell><Data ss:Type="String">Morning (IN)</Data></Cell>
                <Cell><Data ss:Type="String">Morning (OUT)</Data></Cell>
                <Cell><Data ss:Type="String">Afternoon (IN)</Data></Cell>
                <Cell><Data ss:Type="String">Afternoon (OUT)</Data></Cell>
              </Row>
              <Row>
                <Cell><Data ss:Type="String">17.08</Data></Cell>
                <Cell><Data ss:Type="String">Mon</Data></Cell>
                <Cell><Data ss:Type="String">07:30</Data></Cell>
                <Cell><Data ss:Type="String">12:00</Data></Cell>
                <Cell><Data ss:Type="String">13:00</Data></Cell>
                <Cell><Data ss:Type="String">17:30</Data></Cell>
              </Row>
            </Table>
          </Worksheet>
        </Workbook>'''

        file = SimpleUploadedFile('attendance.xml', xml, content_type='application/xml')
        records = AttendanceImportForm().parse_xml(file)

        self.assertTrue(any(record.get('Date') == '2026-08-17' for record in records))
        self.assertTrue(any(record.get('Morning In') == '07:30' for record in records))
        self.assertTrue(any(record.get('Afternoon Out') == '17:30' for record in records))

  def test_incomplete_punch_pairs_are_counted_as_absent(self):
        records = [{
            'Employee Number': 'BIO-001',
            'Date': '2026-08-12',
            'TimeIn': '08:00',
            'Worked Minutes': '480',
        }]

        imported, matched, errors = AttendanceImportService().import_summary_records(records)

        self.assertEqual((imported, matched, errors), (1, 1, 0))
        daily = DailyAttendance.objects.get(staff=self.staff, attendance_date=date(2026, 8, 12))
        self.assertIsNone(daily.check_out)
        self.assertFalse(daily.is_present)
        self.assertEqual(daily.status, 'ABSENT')

  def test_complete_punches_and_overtime_are_persisted(self):
    records = [{
      'Biometric ID': 'BIO-001',
      'Date': '2026-08-13',
      'Morning In': '08:00',
      'Morning Out': '12:00',
      'Afternoon In': '13:00',
      'Afternoon Out': '17:00',
      'Overtime In': '18:00',
      'Overtime Out': '20:00',
    }]

    imported, matched, errors = AttendanceImportService().import_summary_records(records)

    self.assertEqual((imported, matched, errors), (1, 1, 0))
    daily = DailyAttendance.objects.get(staff=self.staff, attendance_date=date(2026, 8, 13))
    self.assertTrue(daily.four_punch_complete)
    self.assertTrue(daily.is_present)
    self.assertEqual(daily.ot_in.hour, 18)
    self.assertEqual(daily.ot_out.hour, 20)
    self.assertEqual(daily.ot_hours_calculated, 2)

  def test_summary_import_is_ignored_when_detailed_time_data_exists_in_same_payroll_half(self):
        records = [
            {
                'Summary': 'MONTHLY',
                'Biometric ID': 'BIO-001',
                'Report Start': '2026-08-16',
                'Report End': '2026-08-31',
                'Working days': '16',
                'Attendance days': '1',
                'Absences days': '15',
            },
            {
                'Biometric ID': 'BIO-001',
                'Date': '2026-08-17',
                'Morning In': '08:26',
                'Morning Out': '',
                'Afternoon In': '',
                'Afternoon Out': '',
            },
        ]

        imported, matched, errors = AttendanceImportService().import_summary_records(records)

        self.assertEqual((imported, matched, errors), (1, 1, 0))
        self.assertFalse(MonthlyAttendanceSummary.objects.filter(staff=self.staff).exists())

        daily = DailyAttendance.objects.get(staff=self.staff, attendance_date=date(2026, 8, 17))
        self.assertFalse(daily.is_present)
        self.assertEqual(daily.status, 'ABSENT')

  def test_first_half_summary_is_preserved_when_only_second_half_has_detailed_time_data(self):
        records = [
            {
                'Summary': 'MONTHLY',
                'Biometric ID': 'BIO-001',
                'Report Start': '2026-08-01',
                'Report End': '2026-08-15',
                'Working days': '15',
                'Attendance days': '1',
                'Absences days': '14',
            },
            {
                'Biometric ID': 'BIO-001',
                'Date': '2026-08-17',
                'Morning In': '08:26',
                'Morning Out': '12:00',
                'Afternoon In': '13:00',
                'Afternoon Out': '17:00',
            },
        ]

        imported, matched, errors = AttendanceImportService().import_summary_records(records)

        self.assertEqual((imported, matched, errors), (2, 2, 0))
        self.assertTrue(MonthlyAttendanceSummary.objects.filter(staff=self.staff, period_start=date(2026, 8, 1), period_end=date(2026, 8, 15)).exists())

        daily = DailyAttendance.objects.get(staff=self.staff, attendance_date=date(2026, 8, 17))
        self.assertTrue(daily.is_present)
        self.assertEqual(daily.status, 'PRESENT')

  def test_form_parses_xml_spreadsheet_rows(self):
        xml = b'''<?xml version="1.0"?>
        <Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
            xmlns:o="urn:schemas-microsoft-com:office:office"
            xmlns:x="urn:schemas-microsoft-com:office:excel"
            xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
          <Worksheet>
            <Table>
              <Row>
                <Cell><Data ss:Type="String">Biometric ID</Data></Cell>
                <Cell><Data ss:Type="String">Date</Data></Cell>
                <Cell><Data ss:Type="String">Status</Data></Cell>
              </Row>
              <Row>
                <Cell><Data ss:Type="String">BIO-001</Data></Cell>
                <Cell><Data ss:Type="String">2026-08-10</Data></Cell>
                <Cell><Data ss:Type="String">Present</Data></Cell>
              </Row>
            </Table>
          </Worksheet>
        </Workbook>'''

        file = SimpleUploadedFile('attendance.xml', xml, content_type='application/xml')
        records = AttendanceImportForm().parse_xml(file)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['Biometric ID'], 'BIO-001')
        self.assertEqual(records[0]['Date'], '2026-08-10')
        self.assertEqual(records[0]['Status'], 'Present')

  def test_form_parses_utf16_semicolon_csv_rows(self):
    csv_data = 'Biometric ID;Date;Morning In;Morning Out;Afternoon In;Afternoon Out\nBIO-001;2026-08-10;08:00;12:00;13:00;17:00\n'.encode('utf-16')
    file = SimpleUploadedFile('attendance.csv', csv_data, content_type='text/csv')
    form = AttendanceImportForm(data={}, files={'import_file': file})

    self.assertTrue(form.is_valid())
    records = form.get_records()
    self.assertEqual(records[0]['Biometric ID'], 'BIO-001')
    self.assertEqual(records[0]['Afternoon Out'], '17:00')

  def test_csv_import_resolves_user_id_and_employee_name_headers(self):
    records = [{
      'User ID': 'BIO-001',
      'Employee Name': 'Ana Santos',
      'Date': '2026-08-14',
      'Morning In': '08:00',
      'Morning Out': '12:00',
      'Afternoon In': '13:00',
      'Afternoon Out': '17:00',
    }]

    imported, matched, errors = AttendanceImportService().import_summary_records(records)

    self.assertEqual((imported, matched, errors), (1, 1, 0))
    daily = DailyAttendance.objects.get(staff=self.staff, attendance_date=date(2026, 8, 14))
    self.assertTrue(daily.is_present)
    self.assertTrue(daily.four_punch_complete)

  def test_csv_scanner_summary_with_question_mark_date_separator(self):
    csv_data = '''Attendance Summary,,,,,,,,,,,,,,,
,,,Company Name:,,,Name:Ana,,,ID:BIO-001,,,Date:26.08.01?26.08.31,,,
,,,Working days:31,,,Attendance days:1,,,Absences days:30,,,Overtime Hours:,,
,,,Device ID:,,Morning,,Afternoon,,Overtime,,,,Morning,,Afternoon,,Overtime,
Date,Week,(IN),(OUT),(IN),(OUT),(IN),(OUT),Date,Week,(IN),(OUT),(IN),(OUT),(IN),(OUT)
08.01,Sat,8:00,12:00,13:00,16:00,17:00,19:00,08.17,Mon,8:00,12:00,13:00,16:00,17:00,19:00
'''.encode('utf-8')
    file = SimpleUploadedFile('scanner.csv', csv_data, content_type='text/csv')
    form = AttendanceImportForm(data={}, files={'import_file': file})

    self.assertTrue(form.is_valid())
    records = form.get_records()
    self.assertTrue(any(record.get('Date') == '2026-08-17' for record in records))
    daily = next(record for record in records if record.get('Date') == '2026-08-17')
    self.assertEqual(daily['Morning In'], '8:00')
    self.assertEqual(daily['Afternoon Out'], '16:00')
    self.assertEqual(daily['Overtime In'], '17:00')
    self.assertEqual(daily['Overtime Out'], '19:00')

  def test_xlsx_scanner_summary_is_parsed_as_attendance_blocks(self):
    workbook = Workbook()
    sheet = workbook.active
    rows = [
      ['Attendance Summary'],
      ['', '', 'Company Name:', '', 'Name:Ana', '', 'ID:BIO-001', '', 'Date:26.08.01?26.08.31'],
      ['Working days:31', '', 'Attendance days:1', '', 'Absences days:30'],
      ['Device ID:', '', 'Morning', '', 'Afternoon', '', 'Overtime'],
      ['Date', 'Week', '(IN)', '(OUT)', '(IN)', '(OUT)', '(IN)', '(OUT)', 'Date', 'Week', '(IN)', '(OUT)', '(IN)', '(OUT)', '(IN)', '(OUT)'],
      ['08.01', 'Sat', '8:00', '12:00', '13:00', '16:00', '17:00', '19:00', '08.17', 'Mon', '8:00', '12:00', '13:00', '16:00', '', ''],
    ]
    for row in rows:
      sheet.append(row)
    stream = io.BytesIO()
    workbook.save(stream)
    file = SimpleUploadedFile('scanner.xlsx', stream.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    records = AttendanceImportForm().parse_excel(file)

    daily = next(record for record in records if record.get('Date') == '2026-08-17')
    self.assertEqual(daily['Afternoon Out'], '16:00')
    self.assertEqual(daily['Overtime In'], None)

  def test_form_parses_ods_spreadsheet_rows(self):
    content = b'''<?xml version="1.0" encoding="UTF-8"?>
    <office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
      xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
      xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
      <office:body><office:spreadsheet><table:table>
        <table:table-row><table:table-cell><text:p>Biometric ID</text:p></table:table-cell><table:table-cell><text:p>Date</text:p></table:table-cell><table:table-cell><text:p>Status</text:p></table:table-cell></table:table-row>
        <table:table-row><table:table-cell><text:p>BIO-001</text:p></table:table-cell><table:table-cell><text:p>2026-08-10</text:p></table:table-cell><table:table-cell><text:p>Present</text:p></table:table-cell></table:table-row>
      </table:table></office:spreadsheet></office:body>
    </office:document-content>'''
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
      archive.writestr('content.xml', content)
    file = SimpleUploadedFile('attendance.ods', stream.getvalue(), content_type='application/vnd.oasis.opendocument.spreadsheet')
    records = AttendanceImportForm().parse_ods(file)

    self.assertEqual(records, [{'Biometric ID': 'BIO-001', 'Date': '2026-08-10', 'Status': 'Present'}])

  def test_form_parses_scanner_ods_monthly_blocks(self):
    content = '''<?xml version="1.0" encoding="UTF-8"?>
    <office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
      xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
      xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
      <office:body><office:spreadsheet><table:table>
        <table:table-row><table:table-cell><text:p>Attendance Summary</text:p></table:table-cell></table:table-row>
        <table:table-row><table:table-cell><text:p>Company Name:</text:p></table:table-cell><table:table-cell><text:p>Name:Ana</text:p></table:table-cell><table:table-cell><text:p>ID:00001</text:p></table:table-cell><table:table-cell><text:p>Date:26.08.01～26.08.31</text:p></table:table-cell></table:table-row>
        <table:table-row><table:table-cell><text:p>Working days:31</text:p></table:table-cell><table:table-cell><text:p>Attendance days:1</text:p></table:table-cell></table:table-row>
        <table:table-row><table:table-cell><text:p>Absences days:30</text:p></table:table-cell></table:table-row>
      </table:table></office:spreadsheet></office:body></office:document-content>'''.encode('utf-8')
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
      archive.writestr('content.xml', content)
    file = SimpleUploadedFile('scanner.ods', stream.getvalue())
    records = AttendanceImportForm(data={}, files={'import_file': file})

    self.assertTrue(records.is_valid())
    parsed = records.get_records()
    self.assertEqual(len(parsed), 1)
    self.assertEqual(parsed[0]['Biometric ID'], '00001')
    self.assertEqual(parsed[0]['Report Start'], '2026-08-01')
    self.assertEqual(parsed[0]['Working days'], '31')

  def test_monthly_report_block_is_imported(self):
    xml = b'''<?xml version="1.0"?>
    <Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet">
      <Worksheet><Table>
        <Row><Cell><Data>Name:Ana</Data></Cell><Cell><Data>ID:BIO-001</Data></Cell><Cell><Data>Date:26.08.01--26.08.31</Data></Cell></Row>
        <Row><Cell><Data>Working days:31</Data></Cell><Cell><Data>Attendance days:1</Data></Cell><Cell><Data>Absences days:30</Data></Cell><Cell><Data>Overtime Hours:</Data></Cell></Row>
        <Row><Cell><Data>Sick hours:</Data></Cell><Cell><Data>Leave Hours:</Data></Cell><Cell><Data>Daily Salary:</Data></Cell><Cell><Data>Real Pay\xef\xbc\x9a1000</Data></Cell></Row>
      </Table></Worksheet>
    </Workbook>'''

    file = SimpleUploadedFile('monthly.xml', xml, content_type='application/xml')
    records = AttendanceImportForm().parse_xml(file)
    imported, matched, errors = AttendanceImportService().import_summary_records(records)

    self.assertEqual((imported, matched, errors), (1, 1, 0))
    summary = MonthlyAttendanceSummary.objects.get(staff=self.staff)
    self.assertEqual(summary.working_days, 31)
    self.assertEqual(summary.attendance_days, 1)
    self.assertEqual(summary.absence_days, 30)
    self.assertEqual(summary.real_pay, 0)

  def test_monthly_import_starts_unapproved(self):
    records = [{
      'Summary': 'MONTHLY', 'Biometric ID': 'BIO-001',
      'Report Start': '2026-08-01', 'Report End': '2026-08-31',
      'Working days': '31', 'Attendance days': '1', 'Absences days': '30',
    }]
    AttendanceImportService().import_summary_records(records)
    summary = MonthlyAttendanceSummary.objects.get(staff=self.staff)
    self.assertEqual(summary.review_status, MonthlyAttendanceSummary.ReviewStatus.IMPORTED)

  def test_duplicate_monthly_upload_updates_existing_record(self):
    original = [{
      'Summary': 'MONTHLY', 'Biometric ID': 'BIO-001',
      'Report Start': '2026-08-01', 'Report End': '2026-08-31',
      'Working days': '31', 'Attendance days': '1', 'Absences days': '30',
    }]
    updated = [{
      'Summary': 'MONTHLY', 'Biometric ID': 'BIO-001',
      'Report Start': '2026-08-01', 'Report End': '2026-08-31',
      'Working days': '20', 'Attendance days': '10', 'Absences days': '11',
    }]

    AttendanceImportService().import_summary_records(original)
    AttendanceImportService().import_summary_records(updated)

    summary = MonthlyAttendanceSummary.objects.get(staff=self.staff)
    self.assertEqual(summary.working_days, 20)
    self.assertEqual(summary.attendance_days, 10)
    self.assertEqual(summary.absence_days, 11)

  def test_unmatched_biometric_ids_are_reported(self):
    records = [{
      'Summary': 'MONTHLY', 'Biometric ID': 'BIO-999',
      'Report Start': '2026-09-01', 'Report End': '2026-09-30',
      'Working days': '30', 'Attendance days': '25', 'Absences days': '5',
    }]

    unmatched = AttendanceImportService.get_unmatched_biometric_ids(records)

    self.assertEqual(unmatched, ['BIO-999'])

  def test_upload_delete_removes_monthly_attendance_data(self):
    daily = DailyAttendance.objects.create(
      staff=self.staff,
      attendance_date=date(2026, 8, 10),
      morning_in='08:00:00',
      morning_out='12:00:00',
      afternoon_in='13:00:00',
      afternoon_out='17:00:00',
      check_in='08:00:00',
      check_out='17:00:00',
      is_present=True,
      status='PRESENT',
      total_work_minutes=540,
    )
    monthly = MonthlyAttendanceSummary.objects.create(
      staff=self.staff,
      period_start=date(2026, 8, 1),
      period_end=date(2026, 8, 31),
      working_days=31,
      attendance_days=1,
      absence_days=30,
    )
    upload = AttendanceUpload.objects.create(
      period_start=date(2026, 8, 1),
      period_end=date(2026, 8, 31),
      source_file=SimpleUploadedFile('august.csv', b'Biometric ID,Date\nBIO-001,2026-08-10\n'),
      source_filename='august.csv',
      unmatched_biometric_ids=[],
    )

    upload.delete()

    self.assertFalse(DailyAttendance.objects.filter(id=daily.id).exists())
    self.assertFalse(MonthlyAttendanceSummary.objects.filter(id=monthly.id).exists())
    self.assertFalse(AttendanceUpload.objects.filter(id=upload.id).exists())

  def test_same_month_upload_replaces_old_imported_data(self):
    original = AttendanceUpload.objects.create(
      period_start=date(2026, 9, 1),
      period_end=date(2026, 9, 30),
      source_file=SimpleUploadedFile('september-old.csv', b'Biometric ID,Date\nBIO-001,2026-09-01\n'),
      source_filename='september-old.csv',
      unmatched_biometric_ids=[],
    )
    DailyAttendance.objects.create(
      staff=self.staff,
      attendance_date=date(2026, 9, 1),
      morning_in='08:00:00',
      morning_out='12:00:00',
      afternoon_in='13:00:00',
      afternoon_out='17:00:00',
      check_in='08:00:00',
      check_out='17:00:00',
      is_present=True,
      status='PRESENT',
      total_work_minutes=540,
    )
    MonthlyAttendanceSummary.objects.create(
      staff=self.staff,
      period_start=date(2026, 9, 1),
      period_end=date(2026, 9, 30),
      working_days=30,
      attendance_days=1,
      absence_days=29,
    )

    replacement_file = SimpleUploadedFile(
      'september-new.csv',
      b'Biometric ID,Date\nBIO-001,2026-09-05\n',
      content_type='text/csv',
    )

    existing_upload = AttendanceUpload.objects.filter(
      period_start__year=2026,
      period_start__month=9,
    ).first()
    if existing_upload:
      DailyAttendance.objects.filter(attendance_date__year=2026, attendance_date__month=9).delete()
      MonthlyAttendanceSummary.objects.filter(period_start__year=2026, period_start__month=9).delete()
      existing_upload.source_file.delete(save=False)
      existing_upload.source_filename = replacement_file.name
      existing_upload.source_file = replacement_file
      existing_upload.save()

    self.assertEqual(AttendanceUpload.objects.filter(period_start__year=2026, period_start__month=9).count(), 1)
    self.assertEqual(DailyAttendance.objects.filter(attendance_date__year=2026, attendance_date__month=9).count(), 0)
    self.assertEqual(MonthlyAttendanceSummary.objects.filter(period_start__year=2026, period_start__month=9).count(), 0)

  def test_clear_monthly_import_data_removes_all_ranges_in_same_month(self):
    DailyAttendance.objects.create(
      staff=self.staff,
      attendance_date=date(2026, 9, 5),
      is_present=True,
      status='PRESENT',
    )
    DailyAttendance.objects.create(
      staff=self.staff,
      attendance_date=date(2026, 9, 25),
      is_present=True,
      status='PRESENT',
    )
    MonthlyAttendanceSummary.objects.create(
      staff=self.staff,
      period_start=date(2026, 9, 1),
      period_end=date(2026, 9, 15),
      attendance_days=4,
    )
    MonthlyAttendanceSummary.objects.create(
      staff=self.staff,
      period_start=date(2026, 9, 1),
      period_end=date(2026, 9, 30),
      attendance_days=8,
    )

    AttendanceImportService.clear_monthly_import_data(
      date(2026, 9, 1),
      date(2026, 9, 15),
    )

    self.assertFalse(DailyAttendance.objects.filter(
      attendance_date__year=2026,
      attendance_date__month=9,
    ).exists())
    self.assertFalse(MonthlyAttendanceSummary.objects.filter(
      period_start__year=2026,
      period_start__month=9,
    ).exists())

  def test_upload_history_preserves_original_file(self):
    upload = AttendanceUpload.objects.create(
      period_start=date(2026, 10, 1),
      period_end=date(2026, 10, 31),
      source_file=SimpleUploadedFile('october.csv', b'Biometric ID,Date\nBIO-999,2026-10-01\n'),
      source_filename='october.csv',
      unmatched_biometric_ids=['BIO-999'],
    )

    self.assertEqual(upload.source_filename, 'october.csv')
    self.assertEqual(upload.source_file.read(), b'Biometric ID,Date\nBIO-999,2026-10-01\n')
    upload.source_file.delete(save=False)
