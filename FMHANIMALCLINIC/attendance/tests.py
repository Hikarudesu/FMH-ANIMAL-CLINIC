from datetime import date
import io
import zipfile

from django.apps import apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from attendance.forms import AttendanceImportForm
from attendance.models import DailyAttendance, MonthlyAttendanceSummary
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
    self.assertEqual(summary.real_pay, 1000)

  def test_monthly_import_starts_unapproved(self):
    records = [{
      'Summary': 'MONTHLY', 'Biometric ID': 'BIO-001',
      'Report Start': '2026-08-01', 'Report End': '2026-08-31',
      'Working days': '31', 'Attendance days': '1', 'Absences days': '30',
    }]
    AttendanceImportService().import_summary_records(records)
    summary = MonthlyAttendanceSummary.objects.get(staff=self.staff)
    self.assertEqual(summary.review_status, MonthlyAttendanceSummary.ReviewStatus.IMPORTED)
