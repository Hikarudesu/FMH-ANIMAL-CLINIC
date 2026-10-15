from datetime import datetime, time
from unittest.mock import patch

from django.test import SimpleTestCase
from django.template import engines
from django.utils import timezone


class SystemDateTimeFormatTests(SimpleTestCase):
    def test_date_time_and_now_tags_use_system_formats(self):
        configured = {
            'system_date_format': 'd/m/Y',
            'system_time_format': 'h:i A',
        }
        instant = timezone.make_aware(datetime(2026, 10, 15, 14, 5))
        template = engines['django'].from_string(
            '{{ instant|date:"F j, Y g:i A" }}|'
            '{{ clock|time:"g:i A" }}|'
            '{{ clock|machine_time }}|'
            '{{ instant|date:"Y-m-d" }}|'
            '{% now "M d, Y" %}'
        )

        with patch(
            'utils.templatetags.system_formats.get_setting',
            side_effect=lambda key, default=None: configured.get(key, default),
        ), patch(
            'utils.templatetags.system_formats.timezone.now',
            return_value=instant,
        ):
            rendered = template.render({
                'instant': instant,
                'clock': time(14, 5),
            })

        self.assertEqual(
            rendered,
            '15/10/2026 02:05 PM|02:05 PM|14:05|2026-10-15|15/10/2026',
        )