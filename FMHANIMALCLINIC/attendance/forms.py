"""Forms for attendance and biometrics management."""
from django import forms
from django.core.exceptions import ValidationError
import csv
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from openpyxl import load_workbook
import xlrd
from .models import DailyAttendance


class AttendanceImportForm(forms.Form):
    """Import one attendance summary for payroll."""

    import_file = forms.FileField(
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.csv,.xls,.xlsx,.ods,.xml,.xlsm',
        }),
        label='Import File',
        help_text='Upload one attendance summary export in CSV, XLS, XLSX, ODS, XLSM, or XML format.',
    )

    def clean(self):
        return super().clean()

    def clean_import_file(self):
        """Validate the import file."""
        file = self.cleaned_data.get('import_file')
        if not file:
            raise ValidationError('Please select a file to import.')

        # Check file size (max 10MB)
        if file.size > 10 * 1024 * 1024:
            raise ValidationError('File size exceeds 10MB limit.')

        # Check file extension
        filename = file.name.lower()
        allowed = ('.csv', '.xls', '.xlsx', '.ods', '.xlsm', '.xml')
        if not any(filename.endswith(ext) for ext in allowed):
            raise ValidationError('Only CSV, XLS, XLSX, ODS, XLSM, and XML spreadsheet files are supported.')

        return file

    @staticmethod
    def _normalise_header(value):
        if value is None:
            return ''
        return re.sub(r'[^a-z0-9]+', ' ', str(value).strip().lower()).strip()

    @staticmethod
    def _extract_cell_value(cell):
        if cell is None:
            return None
        if hasattr(cell, 'value'):
            return cell.value
        return cell

    def parse_csv(self, file):
        """Parse CSV exports with common encodings, delimiters, and scanner layouts."""
        file.seek(0)
        raw_data = file.read()
        decoded_file = None
        for encoding in ('utf-8-sig', 'utf-16', 'utf-16-le', 'utf-16-be', 'cp1252'):
            try:
                decoded_file = raw_data.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if decoded_file is None:
            raise ValidationError('The CSV file encoding is not supported.')

        sample = decoded_file[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=',;\t|')
        except csv.Error:
            dialect = csv.excel

        rows = [list(row) for row in csv.reader(io.StringIO(decoded_file), dialect)]
        rows = [row for row in rows if any(str(value or '').strip() for value in row)]
        if not rows:
            return []

        has_scanner_blocks = any(
            'Name:' in ' '.join(str(value or '') for value in row)
            and 'ID:' in ' '.join(str(value or '') for value in row)
            for row in rows
        )
        if has_scanner_blocks:
            records = []
            for index in range(len(rows)):
                summary = self._extract_summary_block(rows, index)
                if summary:
                    records.append(summary)
            records.extend(self._extract_daily_rows_from_rows(rows))
            if records:
                return records

        headers = [str(value).strip() for value in rows[0]]
        return [
            {
                header: values[index].strip() if index < len(values) and isinstance(values[index], str) else (values[index] if index < len(values) else None)
                for index, header in enumerate(headers) if header
            }
            for values in rows[1:]
            if any(str(value or '').strip() for value in values)
        ]

    def parse_excel(self, file):
        """Parse ordinary XLSX tables and scanner-style repeated employee blocks."""
        file.seek(0)
        wb = load_workbook(file, read_only=True, data_only=True)
        ws = wb.active
        rows = [list(row) for row in ws.iter_rows(values_only=True)]
        rows = [
            [value if value is not None else '' for value in row]
            for row in rows
            if any(value is not None and str(value).strip() for value in row)
        ]
        has_scanner_blocks = any(
            'Name:' in ' '.join(str(value or '') for value in row)
            and 'ID:' in ' '.join(str(value or '') for value in row)
            and 'Date:' in ' '.join(str(value or '') for value in row)
            for row in rows
        )
        if has_scanner_blocks:
            records = []
            for index in range(len(rows)):
                summary = self._extract_summary_block(rows, index)
                if summary:
                    records.append(summary)
            records.extend(self._extract_daily_rows_from_rows(rows))
            if records:
                return records

        if not rows:
            return []

        headers = rows[0]
        records = []

        for row in rows[1:]:
            record = {}
            for i, header in enumerate(headers):
                if header:
                    value = row[i] if i < len(row) else None
                    record[str(header)] = value.strip() if isinstance(value, str) else value
            if any(value is not None for value in record.values()):
                records.append(record)

        return records

    @staticmethod
    def _extract_summary_block(rows, index):
        """Build one summary record from a header row and the immediately following key/value rows."""
        row = rows[index]
        joined = ' '.join(str(value).strip() for value in row if value)
        if 'Name:' not in joined or 'ID:' not in joined or 'Date:' not in joined:
            return None

        identifier = re.search(r'ID\s*:\s*([^\s]+)', joined)
        period = re.search(
            r'Date\s*:\s*(\d{2})\.(\d{2})\.(\d{2})\s*(?:[\-–—~～?]+\s*|\s*)(\d{2})\.(\d{2})(?:\.(\d{2}))?',
            joined,
        )
        if not identifier or not period:
            return None

        start_year, start_month, start_day, end_year, end_month, end_day = period.groups()
        if not end_day:
            for lookahead in rows[index + 1:min(index + 6, len(rows))]:
                lookahead_joined = ' '.join(str(value or '').strip() for value in lookahead if value)
                working_match = re.search(r'Working\s+days\s*[:：]\s*(\d+)', lookahead_joined)
                if working_match:
                    end_day = working_match.group(1)
                    break
            end_day = end_day or '31'

        summary = {
            'Summary': 'MONTHLY',
            'Biometric ID': identifier.group(1),
            'Report Start': f'20{start_year}-{start_month}-{start_day}',
            'Report End': f'20{end_year}-{end_month}-{end_day}',
        }

        for lookahead in rows[index + 1:min(index + 6, len(rows))]:
            for value in lookahead:
                text = str(value or '').strip()
                if not text or 'Name:' in text or 'ID:' in text or 'Date:' in text:
                    continue
                match = re.match(r'^([^:：]+?)\s*[:：]\s*(.*?)\s*$', text)
                if not match:
                    continue
                label, amount = match.groups()
                normalized = AttendanceImportForm._normalise_header(label)
                if not label or normalized in {'real pay', 'name', 'id', 'date'}:
                    continue
                summary[label.strip()] = amount.strip()

        return summary

    @staticmethod
    def _extract_daily_rows_from_rows(rows):
        """Convert scanner export rows like 17.08 / 07:30 / 12:00 / 13:00 / 17:30 into individual daily attendance records."""
        records = []
        current_biometric = None
        current_year = None
        current_month = None

        for index, values in enumerate(rows):
            joined = ' '.join(str(value).strip() for value in values if value)
            if not joined:
                continue

            # Extract biometric ID - look for employee header pattern first.
            # Some exports omit Company Name and only provide: "Name:... ID:00001 Date:...".
            if ('Name:' in joined and 'ID:' in joined) or ('Company Name:' in joined and 'Name:' in joined and 'ID:' in joined):
                id_match = re.search(r'ID\s*:\s*([^\s]+)', joined)
                if id_match:
                    current_biometric = id_match.group(1).strip()

            # Extract report period - handle both complete (26.08.01～26.08.31) and incomplete (26.08.01～26.08.) formats
            report_period = re.search(
                r'Date\s*:\s*(\d{2})\.(\d{2})\.(\d{2})\s*(?:[\-–—~～?]+\s*|\s*)(\d{2})\.(\d{2})(?:\.(\d{2}))?',
                joined,
            )
            if report_period:
                start_year, start_month, start_day, end_year, end_month, end_day = report_period.groups()
                current_year = int(f'20{start_year}')
                current_month = int(start_month)
                
                # If end day is missing, infer from the calendar-day value exported below the header.
                if not end_day:
                    for lookahead in rows[index + 1:min(index + 6, len(rows))]:
                        lookahead_joined = ' '.join(str(v).strip() for v in lookahead if v)
                        working_match = re.search(r'Working\s+days\s*[:：]\s*(\d+)', lookahead_joined)
                        if working_match:
                            end_day = str(working_match.group(1))
                            break
                    if not end_day:
                        end_day = '31'

            if not current_biometric or current_year is None or current_month is None:
                continue

            if len(values) < 6:
                continue

            # Skip header rows - check if first column is "Date"
            if str(values[0]).strip().lower() == 'date':
                continue
            
            # Skip rows with header keywords
            if 'Device ID' in joined:
                continue

            # Helper function to clean time values
            def clean_time(value):
                value = str(value).strip()
                if not value or value in {'-', '--', 'NA', 'N/A'}:
                    return None
                return value

            def parse_day_month(raw_day):
                if not re.fullmatch(r'\d{1,2}[./-]\d{1,2}', str(raw_day).strip()):
                    return None, None

                first_text, second_text = re.split(r'[./-]', str(raw_day).strip())
                try:
                    first_num = int(first_text)
                    second_num = int(second_text)
                except ValueError:
                    return None, None

                if first_num <= 12 and second_num <= 31:
                    return first_num, second_num
                if second_num <= 12 and first_num <= 31:
                    return second_num, first_num
                return None, None

            # EXTRACT LEFT HALF (First 15 days) - columns 0-7
            raw_day = str(values[0]).strip()
            month_value, day_value = parse_day_month(raw_day)
            if month_value is not None and day_value is not None:
                day = day_value
                month = month_value
                if month == 0:
                    month = current_month

                morning_in = clean_time(values[2] if len(values) > 2 else '')
                morning_out = clean_time(values[3] if len(values) > 3 else '')
                afternoon_in = clean_time(values[4] if len(values) > 4 else '')
                afternoon_out = clean_time(values[5] if len(values) > 5 else '')

                if any((morning_in, morning_out, afternoon_in, afternoon_out)):
                    record = {
                        'Biometric ID': current_biometric,
                        'Date': f'{current_year}-{month:02d}-{day:02d}',
                        'Morning In': morning_in,
                        'Morning Out': morning_out,
                        'Afternoon In': afternoon_in,
                        'Afternoon Out': afternoon_out,
                        'Overtime In': clean_time(values[6] if len(values) > 6 else ''),
                        'Overtime Out': clean_time(values[7] if len(values) > 7 else ''),
                    }
                    records.append(record)

            # EXTRACT RIGHT HALF (16-31 days) - from columns 8-15
            if len(values) > 13:
                raw_day_right = str(values[8]).strip()
                month_value, day_value = parse_day_month(raw_day_right)
                if month_value is not None and day_value is not None:
                    day = day_value
                    month = month_value
                    if month == 0:
                        month = current_month

                    morning_in = clean_time(values[10] if len(values) > 10 else '')
                    morning_out = clean_time(values[11] if len(values) > 11 else '')
                    afternoon_in = clean_time(values[12] if len(values) > 12 else '')
                    afternoon_out = clean_time(values[13] if len(values) > 13 else '')

                    if any((morning_in, morning_out, afternoon_in, afternoon_out)):
                        record = {
                            'Biometric ID': current_biometric,
                            'Date': f'{current_year}-{month:02d}-{day:02d}',
                            'Morning In': morning_in,
                            'Morning Out': morning_out,
                            'Afternoon In': afternoon_in,
                            'Afternoon Out': afternoon_out,
                            'Overtime In': clean_time(values[14] if len(values) > 14 else ''),
                            'Overtime Out': clean_time(values[15] if len(values) > 15 else ''),
                        }
                        records.append(record)

        return records

    def parse_ods(self, file):
        """Parse an OpenDocument Spreadsheet (.ods) into row dictionaries."""
        file.seek(0)
        with zipfile.ZipFile(file) as archive:
            content = archive.read('content.xml')
        root = ET.fromstring(content)
        rows = []
        row_tag = '{urn:oasis:names:tc:opendocument:xmlns:table:1.0}table-row'
        cell_tag = '{urn:oasis:names:tc:opendocument:xmlns:table:1.0}table-cell'
        text_tag = '{urn:oasis:names:tc:opendocument:xmlns:text:1.0}p'
        repeat_attribute = '{urn:oasis:names:tc:opendocument:xmlns:table:1.0}number-columns-repeated'

        for row in root.iter(row_tag):
            values = []
            for cell in row.findall(cell_tag):
                value = ' '.join(text.text or '' for text in cell.iter(text_tag)).strip()
                repeat = int(cell.get(repeat_attribute, '1'))
                values.extend([value] * repeat)
            if any(value for value in values):
                rows.append(values)

        if not rows:
            return []

        records = []
        for index, values in enumerate(rows):
            summary = AttendanceImportForm._extract_summary_block(rows, index)
            if summary:
                records.append(summary)
                continue

        daily_records = AttendanceImportForm._extract_daily_rows_from_rows(rows)
        records.extend(daily_records)

        if records:
            return records

        headers = [str(value).strip() for value in rows[0]]
        return [
            {
                header: values[index] if index < len(values) else None
                for index, header in enumerate(headers)
                if header
            }
            for values in rows[1:]
            if any(value for value in values)
        ]

    def parse_xls(self, file):
        """Parse legacy Excel .xls exports from older scanner software or summary spreadsheets."""
        file.seek(0)
        workbook = xlrd.open_workbook(file_contents=file.read())
        sheet = workbook.sheet_by_index(0)
        headers = [str(value).strip() for value in sheet.row_values(0)]
        records = []

        for row_index in range(1, sheet.nrows):
            values = []
            for cell in sheet.row(row_index):
                value = cell.value
                if cell.ctype == xlrd.XL_CELL_DATE:
                    value = xlrd.xldate_as_datetime(value, workbook.datemode)
                values.append(value)
            record = {
                header: values[index] if index < len(values) else None
                for index, header in enumerate(headers)
                if header
            }
            if any(value is not None for value in record.values()):
                records.append(record)

        return records

    def parse_xml(self, file):
        """Parse monthly attendance summary blocks from Excel XML Spreadsheet exports."""
        file.seek(0)
        xml_text = file.read().decode('utf-8-sig', errors='ignore')
        root = ET.fromstring(xml_text)

        rows = []
        for row in root.iter():
            if row.tag.rsplit('}', 1)[-1] != 'Row':
                continue
            values = []
            for cell in row:
                if cell.tag.rsplit('}', 1)[-1] != 'Cell':
                    continue
                data = None
                for child in cell:
                    if child.tag.rsplit('}', 1)[-1] == 'Data':
                        data = child
                        break
                value = data.text if data is not None and data.text is not None else ''
                values.append(value)
            if values:
                rows.append(values)
        records = []
        for index, values in enumerate(rows):
            summary = AttendanceImportForm._extract_summary_block(rows, index)
            if summary:
                records.append(summary)
                continue

        daily_records = AttendanceImportForm._extract_daily_rows_from_rows(rows)
        records.extend(daily_records)

        unique_records = {}
        for record in records:
            if 'Date' in record:
                key = (record['Biometric ID'], record['Date'])
            else:
                key = (record['Biometric ID'], record['Report Start'])
            unique_records[key] = record
        records = list(unique_records.values())
        if records:
            return records

        if not rows:
            return []

        headers = [str(value).strip() for value in rows[0]]
        for values in rows[1:]:
            record = {
                header: values[index] if index < len(values) else None
                for index, header in enumerate(headers)
                if header
            }
            if any(value is not None for value in record.values()):
                records.append(record)
        return records

    @staticmethod
    def detect_file_format(file):
        """Identify spreadsheet type by actual content, with extension as a fallback."""
        filename = (file.name or '').lower()
        file.seek(0)
        signature = file.read(4096)
        file.seek(0)

        if filename.endswith('.ods') or b'office:document-content' in signature or b'content.xml' in signature:
            return 'ods'
        if filename.endswith(('.xlsx', '.xlsm')) or (signature.startswith(b'PK') and b'xl/' in signature):
            return 'xlsx'
        if filename.endswith('.xml') or b'<Workbook' in signature or b'<?xml' in signature:
            return 'xml'
        if filename.endswith('.xls') or (signature.startswith(b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1') and b'Workbook' in signature):
            return 'xls'
        if filename.endswith('.csv') or b',' in signature or b'\n' in signature:
            return 'csv'
        return 'unknown'

    def get_records(self):
        """Parse the uploaded file based on its actual structure and extension."""
        import_file = self.cleaned_data.get('import_file')
        file_type = self.detect_file_format(import_file)

        if file_type == 'csv':
            return self.parse_csv(import_file)
        if file_type in {'xlsx'}:
            return self.parse_excel(import_file)
        if file_type == 'ods':
            return self.parse_ods(import_file)
        if file_type == 'xls':
            import_file.seek(0)
            signature = import_file.read(256).lstrip()
            import_file.seek(0)
            if signature.startswith(b'<?xml') or b'<Workbook' in signature:
                return self.parse_xml(import_file)
            return self.parse_xls(import_file)
        if file_type == 'xml':
            return self.parse_xml(import_file)
        raise ValidationError('Unsupported attendance file format. Supported formats: CSV, XLS, XLSX, ODS, and XML spreadsheet files.') 

class DailyAttendanceForm(forms.ModelForm):
    """Form for manually editing daily attendance records."""
    
    class Meta:
        model = DailyAttendance
        fields = [
            'check_in',
            'check_out',
            'status',
            'is_present',
            'adjustment_notes',
        ]
        widgets = {
            'check_in': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time',
            }),
            'check_out': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time',
            }),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'is_present': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'adjustment_notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Notes about why this was adjusted',
            }),
        }
class AttendanceFilterForm(forms.Form):
    """Form for filtering attendance records."""
    
    staff = forms.ModelChoiceField(
        queryset=None,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label='Staff Member',
    )
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
        }),
        label='From Date',
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
        }),
        label='To Date',
    )
    
    status = forms.MultipleChoiceField(
        required=False,
        choices=DailyAttendance.AttendanceStatus.choices,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        label='Status',
    )
    
    def __init__(self, *args, **kwargs):
        """Initialize with dynamic queryset for staff."""
        super().__init__(*args, **kwargs)
        from employees.models import StaffMember
        self.fields['staff'].queryset = StaffMember.objects.filter(
            is_active=True
        ).order_by('first_name', 'last_name')
