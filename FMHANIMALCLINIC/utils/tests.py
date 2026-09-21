from unittest.mock import Mock

from django.test import SimpleTestCase

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
