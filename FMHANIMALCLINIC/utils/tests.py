from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from utils.templatetags.file_urls import stored_or_static_url


class StoredOrStaticUrlTests(SimpleTestCase):
    @patch('utils.templatetags.file_urls.default_storage.exists')
    def test_existing_uploaded_media_returns_media_url(self, mock_exists):
        mock_exists.return_value = True
        field = Mock()
        field.name = 'image/wellness.jpg'
        field.url = '/media/image/wellness.jpg'

        self.assertEqual(stored_or_static_url(field), '/media/image/wellness.jpg')

    @patch('utils.templatetags.file_urls.default_storage.exists')
    def test_missing_uploaded_media_does_not_fallback_to_static(self, mock_exists):
        mock_exists.return_value = False
        field = Mock()
        field.name = 'image/laboratory.png'
        field.url = '/media/image/laboratory.png'

        self.assertEqual(stored_or_static_url(field), '')
