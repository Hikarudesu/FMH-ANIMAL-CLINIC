import os
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

from accounts.activity_signals import log_medical_record_changes
from accounts.models import ActivityLog
from .models import MedicalRecord
from .models import validate_laboratory_image, validate_medical_file
from .views import _pdf_link_callback
from settings.forms import MedicalRecordsSettingsForm


class MedicalRecordActivitySignalTests(SimpleTestCase):
    @patch('accounts.activity_signals.log_activity')
    def test_creation_logs_current_clinical_signs_field(self, log_activity):
        instance = SimpleNamespace(
            _user=object(),
            _ip_address=None,
            id=1,
            pet=SimpleNamespace(name='Carl'),
            history_clinical_signs='Limping',
        )

        log_medical_record_changes(MedicalRecord, instance, created=True)

        self.assertEqual(
            log_activity.call_args.kwargs['details'],
            'History / Clinical Signs: Limping',
        )
        self.assertEqual(
            log_activity.call_args.kwargs['category'], ActivityLog.Category.MEDICAL,
        )


class MedicalFileValidationTests(SimpleTestCase):
    def test_pdf_requires_pdf_signature(self):
        upload = SimpleUploadedFile('result.pdf', b'not a pdf')

        with self.assertRaises(ValidationError):
            validate_medical_file(upload)

    def test_oversized_file_is_rejected(self):
        upload = SimpleUploadedFile('result.pdf', b'%PDF-' + b'x' * (20 * 1024 * 1024))

        with self.assertRaises(ValidationError):
            validate_medical_file(upload)

    def test_valid_pdf_is_accepted(self):
        upload = SimpleUploadedFile('result.pdf', b'%PDF-1.7 test document')

        validate_medical_file(upload)


class LaboratoryTypeSettingsTests(SimpleTestCase):
    @patch('settings.forms.get_setting')
    def test_laboratory_types_can_be_added_and_duplicates_are_removed(self, get_setting):
        get_setting.side_effect = lambda key, default=None: (
            ['Laboratory Result'] if key == 'medical_laboratory_type_options' else default
        )
        form = MedicalRecordsSettingsForm(data={
            'laboratory_types': 'CBC\nBlood Chemistry\nCBC',
            'default_followup_days': '7',
            'vaccination_reminders': 'on',
            'reminder_days_before': '7',
            'clinical_status_auto_actions': 'on',
        })

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['laboratory_types'], ['CBC', 'Blood Chemistry'])

    @patch('settings.forms.get_setting')
    def test_laboratory_type_list_cannot_be_empty(self, get_setting):
        get_setting.side_effect = lambda key, default=None: (
            ['Laboratory Result'] if key == 'medical_laboratory_type_options' else default
        )
        form = MedicalRecordsSettingsForm(data={
            'laboratory_types': '  \n',
            'default_followup_days': '7',
            'reminder_days_before': '7',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('laboratory_types', form.errors)

    def test_laboratory_images_accept_png_and_jpeg(self):
        for filename in ('result.png', 'result.jpg', 'result.jpeg'):
            with self.subTest(filename=filename):
                upload = SimpleUploadedFile(filename, b'image data')
                validate_laboratory_image(upload)

    def test_laboratory_images_reject_non_image_files(self):
        upload = SimpleUploadedFile('result.pdf', b'%PDF-1.7 test document')

        with self.assertRaises(ValidationError):
            validate_laboratory_image(upload)

    def test_laboratory_images_are_limited_to_10_mb(self):
        upload = SimpleUploadedFile('result.png', b'x' * (10 * 1024 * 1024 + 1))

        with self.assertRaises(ValidationError):
            validate_laboratory_image(upload)


class PdfAssetResolutionTests(SimpleTestCase):
    def test_media_assets_are_resolved_to_local_files(self):
        with tempfile.TemporaryDirectory() as media_root:
            logo_path = os.path.join(media_root, 'branches', 'logo.png')
            os.makedirs(os.path.dirname(logo_path))
            with open(logo_path, 'wb') as logo_file:
                logo_file.write(b'logo')

            with override_settings(MEDIA_ROOT=media_root, MEDIA_URL='/media/'):
                resolved_path = _pdf_link_callback('/media/branches/logo.png', '')

            self.assertEqual(resolved_path, logo_path)
