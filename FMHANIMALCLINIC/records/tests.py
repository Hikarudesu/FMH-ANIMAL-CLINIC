from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from .models import validate_laboratory_image, validate_medical_file


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
