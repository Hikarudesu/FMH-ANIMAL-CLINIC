from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from .models import validate_medical_file


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
