from pathlib import Path
from unittest.mock import Mock, patch

from django import forms
from django.test import SimpleTestCase

from FMHANIMALCLINIC import settings as project_settings
from accounts.forms import UserProfileUpdateForm
from settings.forms import ServiceForm
from utils.templatetags.file_urls import stored_or_static_url


class StoredOrStaticUrlTests(SimpleTestCase):
    def test_existing_uploaded_media_returns_media_url(self):
        field = Mock()
        field.name = 'image/wellness.jpg'
        field.url = '/media/image/wellness.jpg'

        self.assertEqual(stored_or_static_url(field), '/media/image/wellness.jpg')

    def test_uploaded_media_returns_url_even_when_storage_check_fails(self):
        field = Mock()
        field.name = 'image/laboratory.png'
        field.url = '/media/image/laboratory.png'

        self.assertEqual(stored_or_static_url(field), '/media/image/laboratory.png')


class ImageRemovalWidgetTests(SimpleTestCase):
    def test_service_form_uses_clearable_image_widget(self):
        form = ServiceForm()
        self.assertIsInstance(form.fields['image'].widget, forms.ClearableFileInput)

    def test_profile_form_uses_clearable_image_widget(self):
        form = UserProfileUpdateForm()
        self.assertIsInstance(form.fields['profile_picture'].widget, forms.ClearableFileInput)


class RailwayVolumePathTests(SimpleTestCase):
    def test_railway_media_root_falls_back_to_app_volume(self):
        with patch.dict('os.environ', {'RAILWAY_ENVIRONMENT': 'production'}, clear=False):
            path = project_settings._resolve_runtime_path(Path('/tmp/default-media'), 'MEDIA_ROOT', 'media')
            self.assertEqual(path, Path('/app/media'))

    def test_custom_media_root_env_var_takes_priority(self):
        with patch.dict('os.environ', {'MEDIA_ROOT': '/tmp/custom-media'}, clear=False):
            path = project_settings._resolve_runtime_path(Path('/tmp/default-media'), 'MEDIA_ROOT', 'media')
            self.assertEqual(path, Path('/tmp/custom-media'))
