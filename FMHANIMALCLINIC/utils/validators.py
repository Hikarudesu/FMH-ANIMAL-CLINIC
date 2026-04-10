"""
Global validators for the FMH Animal Clinic application.
"""

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

# Maximum file size: 10MB
MAX_IMAGE_SIZE_MB = 10
MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024

# Allowed image extensions
ALLOWED_IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg']


def validate_image_file_size(file):
    """
    Validate that an uploaded image file does not exceed the maximum size.
    Max size: 10MB
    """
    if file.size > MAX_IMAGE_SIZE_BYTES:
        raise ValidationError(
            f'File size must not exceed {MAX_IMAGE_SIZE_MB}MB. '
            f'Your file is {file.size / (1024 * 1024):.2f}MB.'
        )


def validate_image_file_extension(value):
    """
    Validate that an uploaded file has an allowed image extension.
    Allowed formats: .png, .jpg, .jpeg
    """
    validator = FileExtensionValidator(allowed_extensions=ALLOWED_IMAGE_EXTENSIONS)
    return validator(value)


def validate_image_file(file):
    """
    Combined validator for image files.
    Validates both file size (max 10MB) and extension (.png, .jpeg).
    """
    validate_image_file_size(file)
    validate_image_file_extension(file)


# Help text for image upload forms
IMAGE_UPLOAD_HELP_TEXT = "Supported formats: .png, .jpeg (Max 10MB)"
