from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from settings.utils import get_setting


class PayrollSettingsSaveTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username='payroll-settings-admin',
            email='payroll-settings-admin@example.com',
            password='A-secure-test-password-923!',
        )
        self.client.force_login(self.admin)

    def tearDown(self):
        cache.clear()

    def test_payroll_form_saves_overtime_rest_days_and_statutory_switches(self):
        response = self.client.post(reverse('settings:payroll_settings'), {
            'form_type': 'payroll',
            'default_staff_allowance': '2500.00',
            'default_overtime_pay_per_hour': '187.50',
            'default_rest_days': '6',
            'paid_leave_type_options': 'Sick Leave\nEmergency Leave',
            'enable_sss': 'on',
            'sss_rate': '4.50',
            'philhealth_rate': '2.00',
            'enable_pagibig': 'on',
            'pagibig_fixed': '100.00',
        })

        self.assertRedirects(response, reverse('settings:payroll_settings'))
        self.assertEqual(
            Decimal(str(get_setting('payroll_default_overtime_pay_per_hour'))),
            Decimal('187.50'),
        )
        self.assertEqual(get_setting('payroll_default_rest_days'), 6)
        self.assertFalse(get_setting('payroll_auto_statutory'))
        self.assertTrue(get_setting('payroll_enable_sss'))
        self.assertFalse(get_setting('payroll_enable_philhealth'))
        self.assertTrue(get_setting('payroll_enable_pagibig'))