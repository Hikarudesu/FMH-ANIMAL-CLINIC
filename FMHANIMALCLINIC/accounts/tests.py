import json
import re
from datetime import date, datetime, time, timedelta
from urllib.parse import parse_qs, urlsplit

from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.core import mail
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.activity_context import reset_current_actor, set_current_actor
from accounts.models import ActivityLog
from accounts.rbac_models import Module, ModulePermission, Role, SpecialPermission
from branches.models import Branch
from appointments.models import Appointment
from billing.models import CustomerStatement, Service
from employees.models import StaffMember
from inventory.models import Product, StockAdjustment
from patients.models import Pet
from pos.models import Sale, SaleItem
from .forms import PetOwnerRegistrationForm
from .lifecycle import (
    expire_due_owner_accounts,
    resolve_owner_deactivation_on_login,
    schedule_owner_deactivation,
)


@override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }
)
class ReceptionistDashboardMetricsTests(TestCase):
    def test_receptionist_hero_cards_compare_matching_periods(self):
        branch = Branch.objects.create(
            name='Hero Comparison Branch',
            phone_number='09123456789',
            address='1 Clinic Street',
            city='Manila',
            state='NCR',
            zip_code='1000',
        )
        role = Role.objects.get(code='receptionist')
        receptionist = get_user_model().objects.create_user(
            username='hero-comparison-receptionist',
            email='hero-comparison-receptionist@example.com',
            password='A-secure-test-password-923!',
            assigned_role=role,
            branch=branch,
        )
        today = date.today()
        previous_month_end = today.replace(day=1) - relativedelta(days=1)
        previous_month_date = previous_month_end.replace(
            day=min(today.day, previous_month_end.day)
        )
        previous_year_month_start = date(today.year - 1, today.month, 1)
        previous_year_month_end = (
            (previous_year_month_start.replace(day=28) + relativedelta(days=4))
            .replace(day=1) - relativedelta(days=1)
        )
        previous_year_date = previous_year_month_start.replace(
            day=min(today.day, previous_year_month_end.day)
        )

        def create_sale(sale_date, total):
            sale = Sale.objects.create(
                branch=branch,
                total=total,
                status=Sale.Status.COMPLETED,
            )
            sale.created_at = timezone.make_aware(
                datetime.combine(sale_date, time(12, 0))
            )
            sale.save(update_fields=['created_at'])
            return sale

        create_sale(today, 100)
        create_sale(today, 200)
        create_sale(previous_month_date, 50)
        create_sale(today - relativedelta(days=1), 25)
        create_sale(previous_year_date, 500)

        self.client.force_login(receptionist)
        response = self.client.get(reverse('accounts:receptionist_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['transactions_this_month'], 3)
        self.assertEqual(
            response.context['monthly_transactions_comparison']['text'],
            '+200.0% vs last month',
        )
        self.assertEqual(response.context['todays_sales_count'], 2)
        self.assertEqual(
            response.context['daily_sales_comparison']['text'],
            '+100.0% vs yesterday',
        )
        self.assertEqual(response.context['annual_revenue'], 375)
        self.assertEqual(
            response.context['annual_revenue_comparison']['text'],
            '-25.0% vs last year',
        )
        self.assertContains(response, 'Transactions This Month')
        self.assertContains(response, '+200.0% vs last month')
        self.assertContains(response, '+100.0% vs yesterday')
        self.assertContains(response, '-25.0% vs last year')
        self.assertContains(response, 'Year-over-year comparison unavailable')
        self.assertNotContains(response, 'On-hand ·')
        self.assertNotContains(response, 'FMH Animal Clinic - Hero Comparison Branch')

    def test_receptionist_comparisons_show_absolute_increase_when_baseline_is_zero(self):
        branch = Branch.objects.create(
            name='Zero Baseline Comparison Branch',
            phone_number='09123456789',
            address='1 Clinic Street',
            city='Manila',
            state='NCR',
            zip_code='1000',
        )
        receptionist = get_user_model().objects.create_user(
            username='zero-baseline-receptionist',
            email='zero-baseline-receptionist@example.com',
            password='A-secure-test-password-923!',
            assigned_role=Role.objects.get(code='receptionist'),
            branch=branch,
        )
        sale = Sale.objects.create(
            branch=branch,
            total=125,
            status=Sale.Status.COMPLETED,
        )
        sale.created_at = timezone.make_aware(
            datetime.combine(date.today(), time(12, 0))
        )
        sale.save(update_fields=['created_at'])

        self.client.force_login(receptionist)
        response = self.client.get(reverse('accounts:receptionist_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context['monthly_transactions_comparison']['text'],
            '+1 vs last month',
        )
        self.assertEqual(
            response.context['daily_sales_comparison']['text'],
            '+1 vs yesterday',
        )
        self.assertEqual(
            response.context['annual_revenue_comparison']['text'],
            '+₱125 vs last year',
        )
        self.assertNotContains(response, 'New vs')

    def test_receptionist_dashboard_charts_and_metrics_are_branch_scoped(self):
        branch = Branch.objects.create(
            name='Pilar Dashboard Branch',
            phone_number='09123456789',
            address='1 Clinic Street',
            city='Pilar',
            state='Cavite',
            zip_code='4101',
        )
        other_branch = Branch.objects.create(
            name='Other Dashboard Branch',
            phone_number='09123456780',
            address='2 Clinic Street',
            city='Manila',
            state='NCR',
            zip_code='1000',
        )
        role = Role.objects.get(code='receptionist')
        receptionist = get_user_model().objects.create_user(
            username='revenue-trend-receptionist',
            email='revenue-trend-receptionist@example.com',
            password='A-secure-test-password-923!',
            assigned_role=role,
            branch=branch,
        )

        def create_staff(username, first_name, last_name, branch, is_active=True):
            staff_user = get_user_model().objects.create_user(
                username=username,
                password='A-secure-test-password-923!',
                assigned_role=role,
                branch=branch,
            )
            return StaffMember.objects.create(
                first_name=first_name,
                last_name=last_name,
                position=StaffMember.Position.RECEPTIONIST,
                branch=branch,
                is_active=is_active,
                user=staff_user,
            )

        create_staff(
            'pilar-active-staff', 'Pilar', 'Active', branch, is_active=True
        )
        create_staff(
            'pilar-inactive-staff', 'Pilar', 'Inactive', branch, is_active=False
        )
        create_staff(
            'other-branch-staff', 'Other', 'Branch', other_branch, is_active=True
        )
        branch_product = Product.objects.create(
            name='Pilar inventory',
            item_type='Product',
            price=30,
            stock_quantity=2,
            branch=branch,
        )
        branch_medication = Product.objects.create(
            name='Pilar medication',
            item_type='Medication',
            price=0,
            stock_quantity=2,
            branch=branch,
        )
        other_branch_product = Product.objects.create(
            name='Other branch inventory',
            item_type='Medication',
            price=100,
            stock_quantity=10,
            branch=other_branch,
        )
        today = timezone.localdate()
        for appointment_branch, appointment_hour, appointment_status in (
            (branch, 9, Appointment.Status.PENDING),
            (branch, 9, Appointment.Status.CONFIRMED),
            (branch, 17, Appointment.Status.CONFIRMED),
            (branch, 11, Appointment.Status.COMPLETED),
            (other_branch, 10, Appointment.Status.PENDING),
        ):
            Appointment.objects.create(
                owner_name='Dashboard Owner',
                pet_name='Dashboard Pet',
                branch=appointment_branch,
                appointment_date=today,
                appointment_time=time(appointment_hour, 0),
                status=appointment_status,
            )
        current_year = timezone.localdate().year

        for sale_branch, month, amount, status, customer_type in (
            (
                branch, 6, 125, Sale.Status.COMPLETED,
                Sale.CustomerType.REGISTERED,
            ),
            (
                other_branch, 7, 900, Sale.Status.COMPLETED,
                Sale.CustomerType.WALKIN,
            ),
            (
                branch, 8, 500, Sale.Status.VOIDED,
                Sale.CustomerType.WALKIN,
            ),
            (
                branch, 9, 75, Sale.Status.COMPLETED,
                Sale.CustomerType.WALKIN,
            ),
        ):
            sale = Sale.objects.create(
                branch=sale_branch,
                total=amount,
                status=status,
                customer_type=customer_type,
            )
            sale.created_at = timezone.make_aware(
                datetime(current_year, month, 15, 12, 0)
            )
            sale.save(update_fields=['created_at'])

        category_sale = Sale.objects.create(
            branch=branch,
            total=0,
            status=Sale.Status.COMPLETED,
        )
        SaleItem.objects.create(
            sale=category_sale,
            item_type=SaleItem.ItemType.PRODUCT,
            product=branch_product,
            name=branch_product.name,
            unit_price=0,
            quantity=3,
        )
        SaleItem.objects.create(
            sale=category_sale,
            item_type=SaleItem.ItemType.MEDICATION,
            product=branch_medication,
            name=branch_medication.name,
            unit_price=0,
            quantity=4,
        )
        prior_month_category_sale = Sale.objects.create(
            branch=branch,
            total=0,
            status=Sale.Status.COMPLETED,
        )
        prior_month_category_sale.created_at = timezone.now() - relativedelta(
            months=1
        )
        prior_month_category_sale.save(update_fields=['created_at'])
        SaleItem.objects.create(
            sale=prior_month_category_sale,
            item_type=SaleItem.ItemType.PRODUCT,
            product=branch_product,
            name=branch_product.name,
            unit_price=0,
            quantity=99,
        )
        prior_month_category_sale.total = 0
        prior_month_category_sale.save(update_fields=['total'])
        other_branch_category_sale = Sale.objects.create(
            branch=other_branch,
            total=0,
            status=Sale.Status.COMPLETED,
        )
        SaleItem.objects.create(
            sale=other_branch_category_sale,
            item_type=SaleItem.ItemType.MEDICATION,
            product=other_branch_product,
            name=other_branch_product.name,
            unit_price=0,
            quantity=12,
        )

        self.client.force_login(receptionist)
        response = self.client.get(reverse('accounts:receptionist_dashboard'))

        self.assertEqual(response.status_code, 200)
        hourly_data = json.loads(response.context['appointment_hourly_data'])
        self.assertEqual(len(hourly_data), 10)
        self.assertEqual(hourly_data[0], {'hour': '8 AM', 'count': 0})
        self.assertEqual(hourly_data[1], {'hour': '9 AM', 'count': 2})
        self.assertEqual(hourly_data[2], {'hour': '10 AM', 'count': 0})
        self.assertEqual(hourly_data[-1], {'hour': '5 PM', 'count': 1})
        self.assertEqual(response.context['annual_revenue'], 290)
        self.assertEqual(response.context['annual_registered_revenue'], 125)
        self.assertEqual(response.context['annual_walkin_revenue'], 165)
        workload = json.loads(response.context['monthly_appointments'])
        self.assertEqual(len(workload), 6)
        self.assertEqual(workload[-1]['month'], today.strftime('%b %Y'))
        self.assertEqual(workload[-1]['count'], 4)
        self.assertEqual(sum(month['count'] for month in workload), 4)
        self.assertContains(response, 'Monthly Appointments')
        self.assertContains(response, 'Last 6 months')
        self.assertContains(response, 'id="monthlyAppointmentsChart"')
        self.assertContains(response, 'id="monthlyRevenueChart"')
        self.assertContains(response, 'Monthly Revenue')
        self.assertContains(response, f'January - December {current_year}')
        self.assertContains(response, 'Sales by Category')
        self.assertContains(response, 'This Month')
        self.assertContains(response, 'container-type: inline-size')
        self.assertContains(response, 'font-size: clamp(18px, 14cqi, 28px)')
        dashboard_html = response.content.decode()
        self.assertLess(
            dashboard_html.index('id="categorySalesChart"'),
            dashboard_html.index('id="categorySalesDetails"'),
        )
        self.assertContains(response, 'category-sales-body')
        self.assertContains(response, 'category-sales-header')
        self.assertContains(response, 'padding: 10px 18px 12px')
        self.assertContains(response, 'width: min(100%, 164px)')
        self.assertContains(response, 'min-height: 0')
        self.assertContains(response, '.charts-row.appointments-category-row')
        self.assertContains(response, '@container category-sales (max-width: 260px)')
        self.assertContains(response, '@media (max-width: 760px)')
        self.assertContains(response, '@media (max-width: 640px)')
        self.assertNotContains(response, 'Total sales this month')
        self.assertNotContains(response, 'category-sales-total')
        monthly_revenue = json.loads(response.context['monthly_revenue_data'])
        self.assertEqual(len(monthly_revenue), 12)
        self.assertEqual(monthly_revenue[5], {'month': 'June', 'revenue': 125.0})
        self.assertEqual(monthly_revenue[6], {'month': 'July', 'revenue': 0.0})
        self.assertEqual(monthly_revenue[8], {'month': 'September', 'revenue': 75.0})
        self.assertContains(response, 'Revenue This Year')
        self.assertContains(response, 'Inventory Value')
        dashboard_html = response.content.decode()
        self.assertLess(
            dashboard_html.index('Transactions This Month'),
            dashboard_html.index('Sales Today'),
        )
        self.assertLess(
            dashboard_html.index('Sales Today'),
            dashboard_html.index('Revenue This Year'),
        )
        category_sales = json.loads(response.context['category_sales'])
        self.assertEqual(
            {item['type']: item['count'] for item in category_sales},
            {
                SaleItem.ItemType.PRODUCT: 1,
                SaleItem.ItemType.MEDICATION: 1,
            },
        )
        self.assertNotContains(response, 'Appointment Status')
        self.assertNotContains(response, 'Booking Source')
        self.assertNotContains(response, 'Top 5 Selling Products')
        self.assertNotContains(response, 'appointmentSourceChart')
        self.assertNotContains(response, 'topProductsChart')
        self.assertContains(response, '₱')
        self.assertNotContains(response, 'â‚±')
        self.assertNotContains(response, 'Hourly Appointment Volume / Peak Traffic Today')
        self.assertNotContains(response, 'Most-Ordered Product Categories')
        self.assertContains(response, '<div class="hero-stats">')
        self.assertEqual(response.content.count(b'class="hero-stat-card'), 4)
        self.assertEqual(response.context['active_staff'], 1)
        self.assertEqual(response.context['total_staff'], 2)
        self.assertEqual(response.context['total_inventory_value'], 60)
        self.assertEqual(response.context['completed_visits_this_month'], 0)
        self.assertEqual(response.context['scheduled_appointments_this_month'], 0)
        self.assertContains(response, 'Front Desk Dashboard')
        self.assertNotContains(response, 'page-hero-actions')
        self.assertContains(
            response,
            f'href="{reverse("accounts:receptionist_dashboard")}"',
        )

@override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }
)
class ReceptionistDashboardRoutingTests(TestCase):
    def setUp(self):
        role = Role.objects.get(code='receptionist')
        self.receptionist = get_user_model().objects.create_user(
            username='dashboard-route-receptionist',
            email='dashboard-route-receptionist@example.com',
            password='A-secure-test-password-923!',
            assigned_role=role,
        )
        self.client.force_login(self.receptionist)

    def test_receptionist_login_and_admin_dashboard_route_use_receptionist_dashboard(self):
        expected_url = reverse('accounts:receptionist_dashboard')

        login_response = self.client.get(reverse('accounts:login_page'))
        admin_response = self.client.get(reverse('accounts:admin_dashboard'))

        self.assertRedirects(login_response, expected_url)
        self.assertRedirects(admin_response, expected_url)

    def test_receptionist_dashboard_route_renders_receptionist_content(self):
        response = self.client.get(reverse('accounts:receptionist_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/receptionist_dashboard.html')
        self.assertContains(response, 'Monthly Appointments')
        self.assertContains(response, 'Front Desk Dashboard')
        self.assertContains(response, 'Monthly Revenue')
        self.assertNotContains(response, 'Booking Source')
        self.assertNotContains(response, 'Top 5 Selling Products')
        self.assertNotContains(response, 'Revenue by Branch')
        self.assertNotContains(response, 'Most Appointed Branches')


@override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }
)
class VetDashboardContentTests(TestCase):
    def test_veterinarian_and_assistant_dashboards_omit_clinical_insights(self):
        branch = Branch.objects.create(
            name='Vet Dashboard Branch',
            phone_number='09123456789',
            address='1 Clinic Street',
            city='Manila',
            state='NCR',
            zip_code='1000',
        )

        for role_code, dashboard_title in (
            ('veterinarian', 'Veterinarian Dashboard'),
            ('assistant_veterinarian', 'Vet Assistant Dashboard'),
        ):
            with self.subTest(role=role_code):
                role, _ = Role.objects.get_or_create(
                    code=role_code,
                    defaults={
                        'name': role_code.replace('_', ' ').title(),
                        'hierarchy_level': 5,
                        'is_staff_role': True,
                    },
                )
                user = get_user_model().objects.create_user(
                    username=f'{role_code}-dashboard-content',
                    email=f'{role_code}-dashboard-content@example.com',
                    password='A-secure-test-password-923!',
                    assigned_role=role,
                    branch=branch,
                )
                self.client.force_login(user)

                response = self.client.get(reverse('vet_dashboard'))

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, dashboard_title)
                self.assertNotContains(response, 'page-hero-actions')
                self.assertNotContains(response, 'Clinical Insights')
                self.assertNotContains(response, 'Patient Flow')
                self.assertNotContains(response, 'Clinical Activity')
                self.assertNotContains(response, 'Monthly Summary')
                self.assertNotContains(response, 'My Appointments &amp; Any Available Vet Today')
                self.assertNotContains(response, "This Week's Schedule")
                self.assertNotContains(response, 'Upcoming Appointments')
                self.assertNotContains(response, 'monthlyPerformanceChart')
                self.assertContains(response, 'Recent Medical Records')
                self.assertContains(response, 'No medical records have been recorded yet.')
                dashboard_html = response.content.decode()
                self.assertLess(
                    dashboard_html.index('Your Completed Consultations'),
                    dashboard_html.index('Appointment Types'),
                )
                self.assertLess(
                    dashboard_html.index('Appointment Types'),
                    dashboard_html.index('Patient Status'),
                )
                self.assertContains(response, 'charts-row-monthly')
                self.assertContains(response, 'charts-row-supporting')
                self.assertContains(response, 'chart-body-monthly')
                self.assertContains(response, 'monthlyCompletedConsultationsChart')
                self.assertNotContains(response, 'weeklyWorkloadChart')

    def test_veterinarian_dashboard_shows_recent_branch_medical_entries(self):
        from records.models import MedicalRecord, RecordEntry

        branch = Branch.objects.create(
            name='Recent Records Branch',
            phone_number='09123456789',
            address='1 Clinic Street',
            city='Manila',
            state='NCR',
            zip_code='1000',
        )
        other_branch = Branch.objects.create(
            name='Other Recent Records Branch',
            phone_number='09123456780',
            address='2 Clinic Street',
            city='Manila',
            state='NCR',
            zip_code='1000',
        )
        role = Role.objects.get(code='veterinarian')
        medical_records_module, _ = Module.objects.get_or_create(
            code='medical_records',
            defaults={'name': 'Medical Records'},
        )
        ModulePermission.objects.get_or_create(
            role=role,
            module=medical_records_module,
            permission_type=ModulePermission.PermissionType.CREATE,
        )
        user = get_user_model().objects.create_user(
            username='vet-recent-records',
            email='vet-recent-records@example.com',
            password='A-secure-test-password-923!',
            assigned_role=role,
            branch=branch,
        )
        staff = StaffMember.objects.create(
            first_name='Recent',
            last_name='Vet',
            position=StaffMember.Position.VETERINARIAN,
            branch=branch,
            user=user,
        )

        visible_pet = Pet.objects.create(
            branch=branch,
            name='Visible Patient',
            species='Dog',
            sex=Pet.Sex.MALE,
        )
        visible_record = MedicalRecord.objects.create(
            pet=visible_pet,
            vet=staff,
            branch=branch,
            date_recorded=timezone.localdate(),
        )
        visible_entry = RecordEntry.objects.create(
            record=visible_record,
            vet=staff,
            date_recorded=timezone.localdate(),
            history_clinical_signs='Recent patient has mild seasonal itching.',
        )
        backdated_entry = RecordEntry.objects.create(
            record=visible_record,
            vet=staff,
            date_recorded=timezone.localdate() - timedelta(days=30),
            history_clinical_signs='Recently saved backdated visit.',
        )
        RecordEntry.objects.filter(pk=backdated_entry.pk).update(
            created_at=timezone.now() + timedelta(minutes=1),
        )

        hidden_pet = Pet.objects.create(
            branch=other_branch,
            name='Other Branch Patient',
            species='Cat',
            sex=Pet.Sex.FEMALE,
        )
        hidden_record = MedicalRecord.objects.create(
            pet=hidden_pet,
            branch=other_branch,
            date_recorded=timezone.localdate(),
        )
        RecordEntry.objects.create(
            record=hidden_record,
            date_recorded=timezone.localdate(),
            history_clinical_signs='Must not appear on the veterinarian dashboard.',
        )

        self.client.force_login(user)
        response = self.client.get(reverse('vet_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Visible Patient')
        self.assertContains(response, 'mild seasonal itching')
        self.assertContains(response, 'Recently saved backdated visit.')
        self.assertNotContains(response, 'Other Branch Patient')
        self.assertNotContains(response, 'Must not appear on the veterinarian dashboard.')
        self.assertContains(response, 'View All')
        self.assertContains(response, 'New Record')
        self.assertContains(response, reverse('records:admin_create'))
        self.assertContains(
            response,
            reverse('records:admin_detail', args=[visible_record.pk]),
        )
        self.assertEqual(
            response.context['recent_medical_records'][0].pk,
            backdated_entry.pk,
        )
        self.assertNotEqual(
            response.context['recent_medical_records'][0].pk,
            visible_entry.pk,
        )

    def test_monthly_consultation_chart_requires_matching_vet_and_counts_appointments_once(self):
        from records.models import MedicalRecord, RecordEntry

        today = timezone.localdate()
        if today.month < 6:
            self.skipTest('The June-to-current-month chart has no months before June.')

        branch = Branch.objects.create(
            name='Monthly Consultations Branch',
            phone_number='09123456789',
            address='1 Clinic Street',
            city='Manila',
            state='NCR',
            zip_code='1000',
        )
        role = Role.objects.get(code='veterinarian')
        user = get_user_model().objects.create_user(
            username='vet-monthly-consultations',
            email='vet-monthly-consultations@example.com',
            password='A-secure-test-password-923!',
            assigned_role=role,
            branch=branch,
        )
        staff = StaffMember.objects.create(
            first_name='Monthly',
            last_name='Vet',
            position=StaffMember.Position.VETERINARIAN,
            branch=branch,
            user=user,
        )
        other_user = get_user_model().objects.create_user(
            username='other-monthly-vet',
            email='other-monthly-vet@example.com',
            password='A-secure-test-password-923!',
            assigned_role=role,
            branch=branch,
        )
        other_vet = StaffMember.objects.create(
            first_name='Other',
            last_name='Vet',
            position=StaffMember.Position.VETERINARIAN,
            branch=branch,
            user=other_user,
        )
        pet = Pet.objects.create(
            branch=branch,
            name='Monthly Patient',
            species='Dog',
            sex=Pet.Sex.MALE,
        )
        record = MedicalRecord.objects.create(
            pet=pet,
            vet=staff,
            branch=branch,
            date_recorded=date(today.year, 6, 15),
        )

        def create_completed_appointment(preferred_vet=staff):
            return Appointment.objects.create(
                owner_name='Monthly Patient Owner',
                pet_name=pet.name,
                pet=pet,
                branch=branch,
                preferred_vet=preferred_vet,
                appointment_date=date(today.year, 6, 15),
                appointment_time=time(9, 0),
                status=Appointment.Status.COMPLETED,
            )

        assigned_appointment = create_completed_appointment()
        RecordEntry.objects.create(
            record=record,
            appointment=assigned_appointment,
            vet=staff,
            date_recorded=date(today.year, 6, 15),
        )
        RecordEntry.objects.create(
            record=record,
            appointment=assigned_appointment,
            vet=staff,
            date_recorded=date(today.year, 6, 15),
        )

        fallback_appointment = create_completed_appointment()
        RecordEntry.objects.create(
            record=record,
            appointment=fallback_appointment,
            date_recorded=date(today.year, 6, 15),
        )

        mismatched_entry_appointment = create_completed_appointment()
        RecordEntry.objects.create(
            record=record,
            appointment=mismatched_entry_appointment,
            vet=other_vet,
            date_recorded=date(today.year, 6, 15),
        )

        other_assigned_appointment = create_completed_appointment(other_vet)
        RecordEntry.objects.create(
            record=record,
            appointment=other_assigned_appointment,
            vet=staff,
            date_recorded=date(today.year, 6, 15),
        )

        self.client.force_login(user)
        response = self.client.get(reverse('vet_dashboard'))

        self.assertEqual(response.status_code, 200)
        labels = response.context['monthly_consultation_labels']
        counts = response.context['monthly_consultation_counts']
        self.assertEqual(labels[0], 'Jun')
        self.assertEqual(counts[0], 2)
        self.assertEqual(
            len(labels),
            today.month - 5,
        )


@override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }
)
class UserPortalDashboardTests(TestCase):
    def test_dashboard_serializes_data_for_every_chart(self):
        owner = get_user_model().objects.create_user(
            username='dashboard-owner',
            email='dashboard-owner@example.com',
            password='A-secure-test-password-923!',
        )
        self.client.force_login(owner)

        response = self.client.get(reverse('accounts:user_dashboard'))

        self.assertEqual(response.status_code, 200)
        for context_key in (
            'monthly_spending_json',
            'appointment_history_json',
            'spending_breakdown_json',
        ):
            with self.subTest(context_key=context_key):
                self.assertIn(context_key, response.context)
                self.assertIsInstance(
                    json.loads(response.context[context_key]), list
                )
        monthly_spending = json.loads(response.context['monthly_spending_json'])
        self.assertEqual(
            [month['month'] for month in monthly_spending],
            [
                'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
            ],
        )
        self.assertEqual(len(monthly_spending), 12)
        self.assertContains(
            response,
            f'January–December {timezone.localdate().year}',
        )
        appointment_history = json.loads(
            response.context['appointment_history_json']
        )
        self.assertEqual(len(appointment_history), 6)
        self.assertTrue(
            all(month['count'] == 0 for month in appointment_history)
        )
        self.assertNotIn(b'const monthlySpending = ;', response.content)
        self.assertNotContains(response, 'Visits Per Pet')
        self.assertNotContains(response, 'visitsPerPetChart')
        self.assertNotIn('visits_per_pet_json', response.context)
        self.assertNotContains(response, 'Pet Health Overview')
        self.assertNotContains(response, 'petHealthChart')
        self.assertIn('appointment-history-row', response.content.decode())
        self.assertContains(response, 'Monthly Spending')
        self.assertContains(response, 'Appointment History')
        self.assertContains(response, 'Completed visits per month')
        self.assertNotContains(response, 'Appointment Status')
        self.assertNotContains(response, 'appointmentStatusChart')
        self.assertNotContains(response, 'page-hero-actions')
        self.assertNotContains(response, 'Pet Health at a Glance')
        self.assertNotContains(response, 'Quick Insights')
        self.assertNotContains(response, 'Reservations')
        self.assertNotContains(response, 'This Month')
        self.assertNotIn('pet_species_json', response.context)
        self.assertNotIn('pet_health_list', response.context)

    def test_appointment_history_shows_branch_scoped_completed_visits_for_six_months(self):
        today = timezone.localdate()
        owner_branch = Branch.objects.create(
            name='Appointment History Branch',
            phone_number='09123456789',
            address='1 Clinic Street',
            city='Manila',
            state='NCR',
            zip_code='1000',
        )
        other_branch = Branch.objects.create(
            name='Other Appointment History Branch',
            phone_number='09123456789',
            address='2 Clinic Street',
            city='Manila',
            state='NCR',
            zip_code='1000',
        )
        owner = get_user_model().objects.create_user(
            username='appointment-history-owner',
            email='appointment-history-owner@example.com',
            password='A-secure-test-password-923!',
            branch=owner_branch,
        )
        pet = Pet.objects.create(
            owner=owner,
            branch=owner_branch,
            name='History Pet',
            species='Dog',
            sex=Pet.Sex.MALE,
        )
        first_month = today.replace(day=1) - relativedelta(months=5)
        for offset in range(6):
            appointment_date = first_month + relativedelta(months=offset)
            Appointment.objects.create(
                owner_name=owner.get_full_name() or owner.username,
                pet_name=pet.name,
                pet=pet,
                branch=owner_branch,
                appointment_date=appointment_date,
                appointment_time=time(9, 0),
                status=Appointment.Status.COMPLETED,
                user=owner,
            )

        Appointment.objects.create(
            owner_name=owner.username,
            pet_name=pet.name,
            pet=pet,
            branch=owner_branch,
            appointment_date=today.replace(day=1),
            appointment_time=time(10, 0),
            status=Appointment.Status.PENDING,
            user=owner,
        )
        Appointment.objects.create(
            owner_name=owner.username,
            pet_name=pet.name,
            pet=pet,
            branch=other_branch,
            appointment_date=today.replace(day=1),
            appointment_time=time(11, 0),
            status=Appointment.Status.COMPLETED,
            user=owner,
        )
        Appointment.objects.create(
            owner_name=owner.username,
            pet_name=pet.name,
            pet=pet,
            branch=owner_branch,
            appointment_date=first_month - relativedelta(months=1),
            appointment_time=time(12, 0),
            status=Appointment.Status.COMPLETED,
            user=owner,
        )

        self.client.force_login(owner)
        response = self.client.get(reverse('accounts:user_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Appointment History Branch')
        page_hero = response.content.decode().split(
            '<div class="page-hero">', 1
        )[1].split('</div>\n</div>', 1)[0]
        self.assertIn('page-hero-branch-badge', page_hero)
        self.assertLess(
            page_hero.index('page-hero-branch-badge'),
            page_hero.index('page-hero-actions')
            if 'page-hero-actions' in page_hero
            else len(page_hero),
        )
        appointment_history = json.loads(
            response.context['appointment_history_json']
        )
        self.assertEqual(len(appointment_history), 6)
        self.assertEqual(
            appointment_history[0]['month'],
            first_month.strftime('%b %Y'),
        )
        self.assertEqual(
            [month['count'] for month in appointment_history],
            [1, 1, 1, 1, 1, 1],
        )

    def test_monthly_spending_chart_aggregates_current_year_completed_sales(self):
        owner = get_user_model().objects.create_user(
            username='monthly-spending-owner',
            email='monthly-spending-owner@example.com',
            password='A-secure-test-password-923!',
        )
        current_year = timezone.localdate().year
        branch = Branch.objects.create(
            name='Monthly Spending Branch',
            phone_number='09123456789',
            address='1 Clinic Street',
            city='Manila',
            state='NCR',
            zip_code='1000',
        )
        for month, amount, status, year in (
            (1, 125, Sale.Status.COMPLETED, current_year),
            (1, 75, Sale.Status.COMPLETED, current_year),
            (6, 300, Sale.Status.COMPLETED, current_year),
            (7, 999, Sale.Status.COMPLETED, current_year),
            (2, 888, Sale.Status.VOIDED, current_year),
            (3, 777, Sale.Status.COMPLETED, current_year - 1),
        ):
            sale = Sale.objects.create(
                branch=branch,
                customer=owner,
                total=amount,
                status=status,
            )
            sale.completed_at = timezone.make_aware(
                datetime(year, month, 15, 12, 0)
            )
            sale.save(update_fields=['completed_at'])

        self.client.force_login(owner)
        response = self.client.get(reverse('accounts:user_dashboard'))

        self.assertEqual(response.status_code, 200)
        monthly_spending = json.loads(response.context['monthly_spending_json'])
        self.assertEqual(monthly_spending[0], {'month': 'Jan', 'total': 200.0})
        self.assertEqual(monthly_spending[1], {'month': 'Feb', 'total': 0.0})
        self.assertEqual(monthly_spending[5], {'month': 'Jun', 'total': 300.0})
        self.assertEqual(monthly_spending[6], {'month': 'Jul', 'total': 999.0})
        self.assertEqual(monthly_spending[11], {'month': 'Dec', 'total': 0.0})
        self.assertEqual(response.context['monthly_spending_year'], current_year)
        self.assertEqual(response.context['completed_transaction_count'], 5)
        self.assertContains(response, 'Completed Transactions')
        dashboard_html = response.content.decode()
        self.assertLess(
            dashboard_html.index('Pending Follow-ups'),
            dashboard_html.index('Completed Transactions'),
        )

    def test_spending_breakdown_uses_completed_sales_linked_to_owner(self):
        owner_branch = Branch.objects.create(
            name='Owner Home Branch',
            phone_number='09123456789',
            address='1 Clinic Street',
            city='Manila',
            state='NCR',
            zip_code='1000',
        )
        sale_branch = Branch.objects.create(
            name='Spending Purchase Branch',
            phone_number='09123456789',
            address='2 Clinic Street',
            city='Manila',
            state='NCR',
            zip_code='1000',
        )
        owner = get_user_model().objects.create_user(
            username='spending-dashboard-owner',
            email='spending-dashboard-owner@example.com',
            password='A-secure-test-password-923!',
            branch=owner_branch,
        )
        sale = Sale.objects.create(
            branch=sale_branch,
            customer=owner,
            status=Sale.Status.COMPLETED,
        )
        SaleItem.objects.create(
            sale=sale,
            item_type=SaleItem.ItemType.SERVICE,
            name='Consultation',
            unit_price=250,
            quantity=1,
        )
        SaleItem.objects.create(
            sale=sale,
            item_type=SaleItem.ItemType.PRODUCT,
            name='Pet food',
            unit_price=300,
            quantity=2,
            discount=100,
        )

        self.client.force_login(owner)
        response = self.client.get(reverse('accounts:user_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context['spending_breakdown'],
            [
                {
                    'category': 'Products',
                    'total': 500.0,
                    'icon': 'bx-package',
                    'color': '#3b82f6',
                    'percentage': 66.7,
                },
                {
                    'category': 'Services',
                    'total': 250.0,
                    'icon': 'bx-briefcase',
                    'color': '#009688',
                    'percentage': 33.3,
                },
            ],
        )
        self.assertIn('spendingChart', response.content.decode())
        self.assertContains(response, 'generateLabels(chart)')
        self.assertContains(response, 'chart.data.labels.map((label, index)')


@override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }
)
class AdminDashboardQuickInsightsTests(TestCase):
    def test_quick_insights_show_products_and_services_without_branch_performance(self):
        admin = get_user_model().objects.create_superuser(
            username='quick-insights-admin',
            email='quick-insights-admin@example.com',
            password='A-secure-test-password-923!',
        )
        self.client.force_login(admin)

        response = self.client.get(reverse('accounts:admin_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Top Products')
        self.assertContains(response, 'Top Services')
        self.assertNotContains(response, 'Branch Performance')
        self.assertIn('top_products', response.context)
        self.assertIn('service_breakdown', response.context)
        self.assertContains(response, 'Top Products by Units Sold')
        self.assertContains(response, 'Top Services by Completed Sales')
        self.assertContains(response, 'All branches')
        self.assertContains(response, 'Total User Accounts')

    def test_monthly_performance_chart_replaces_combined_revenue_chart(self):
        admin = get_user_model().objects.create_superuser(
            username='monthly-performance-admin',
            email='monthly-performance-admin@example.com',
            password='A-secure-test-password-923!',
        )
        first_branch = Branch.objects.create(
            name='Monthly Performance Branch One',
            phone_number='09123456789',
            address='1 Clinic Street',
            city='Manila',
            state='NCR',
            zip_code='1000',
        )
        second_branch = Branch.objects.create(
            name='Monthly Performance Branch Two',
            phone_number='09123456780',
            address='2 Clinic Street',
            city='Manila',
            state='NCR',
            zip_code='1000',
        )
        today = timezone.localdate()
        for name, branch, source in (
            ('Portal Patient One', first_branch, Pet.Source.PORTAL),
            ('Portal Patient Two', second_branch, Pet.Source.PORTAL),
            ('Walk-in Patient One', first_branch, Pet.Source.WALKIN),
            ('Walk-in Patient Two', second_branch, Pet.Source.WALKIN),
        ):
            pet = Pet.objects.create(
                branch=branch,
                name=name,
                species='Dog',
                sex=Pet.Sex.MALE,
                source=source,
            )
            pet.created_at = timezone.make_aware(
                datetime.combine(today, time(12, 0))
            )
            pet.save(update_fields=['created_at'])

        self.client.force_login(admin)
        response = self.client.get(reverse('accounts:admin_dashboard'))

        self.assertEqual(response.status_code, 200)
        performance = json.loads(response.context['monthly_performance_data'])
        self.assertEqual(len(performance['labels']), 6)
        self.assertEqual(performance['labels'][-1], today.strftime('%b'))
        self.assertEqual(performance['portal'][-1], 2)
        self.assertEqual(performance['walkin'][-1], 2)
        self.assertContains(response, 'Monthly Performance')
        self.assertContains(response, 'New patient registrations by source')
        self.assertContains(response, 'id="adminMonthlyPerformanceChart"')
        self.assertNotContains(response, 'Combined Revenue Across All Branches')
        self.assertNotContains(response, 'id="revenueChart"')

    def test_total_user_accounts_card_is_second_in_admin_dashboard(self):
        admin = get_user_model().objects.create_superuser(
            username='user-count-admin',
            email='user-count-admin@example.com',
            password='A-secure-test-password-923!',
        )
        get_user_model().objects.create_user(
            username='user-count-owner',
            email='user-count-owner@example.com',
            password='A-secure-test-password-923!',
        )
        self.client.force_login(admin)

        response = self.client.get(reverse('accounts:admin_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_users'], 2)
        dashboard_html = response.content.decode()
        hero_stats = dashboard_html.split('<div class="hero-stats">', 1)[1].split(
            '<!-- ALERT BANNER', 1
        )[0]
        self.assertLess(
            hero_stats.index('Active Staff'),
            hero_stats.index('Total User Accounts'),
        )
        self.assertLess(
            hero_stats.index('Total User Accounts'),
            hero_stats.index('Sales Revenue This Year'),
        )

    def test_quick_insights_aggregate_completed_sales_across_all_branches(self):
        admin = get_user_model().objects.create_superuser(
            username='cross-branch-insights-admin',
            email='cross-branch-insights-admin@example.com',
            password='A-secure-test-password-923!',
        )
        branches = [
            Branch.objects.create(
                name=f'Insights Branch {index}',
                phone_number=f'0912345678{index}',
                address=f'{index} Clinic Street',
                city='Manila',
                state='NCR',
                zip_code='1000',
            )
            for index in (1, 2)
        ]
        products = [
            Product.objects.create(
                name='Popular Product',
                branch=branch,
                price=100,
            )
            for branch in branches
        ]
        wellness_service = Service.objects.create(
            name='Wellness Examination',
            price=500,
        )

        for branch, product, quantity in zip(branches, products, (2, 3)):
            sale = Sale.objects.create(
                branch=branch,
                status=Sale.Status.COMPLETED,
            )
            SaleItem.objects.create(
                sale=sale,
                item_type=SaleItem.ItemType.PRODUCT,
                product=product,
                name=product.name,
                unit_price=product.price,
                quantity=quantity,
            )
            SaleItem.objects.create(
                sale=sale,
                item_type=SaleItem.ItemType.SERVICE,
                service=wellness_service,
                name=wellness_service.name,
                unit_price=wellness_service.price,
            )

        voided_sale = Sale.objects.create(
            branch=branches[1],
            status=Sale.Status.VOIDED,
        )
        SaleItem.objects.create(
            sale=voided_sale,
            item_type=SaleItem.ItemType.PRODUCT,
            product=products[1],
            name=products[1].name,
            unit_price=products[1].price,
            quantity=100,
        )

        self.client.force_login(admin)
        response = self.client.get(reverse('accounts:admin_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context['top_products'][0]['name'],
            'Popular Product',
        )
        self.assertEqual(response.context['top_products'][0]['units_sold'], 5)
        self.assertEqual(
            response.context['service_breakdown'][0]['name'],
            'Wellness Examination',
        )
        self.assertEqual(
            response.context['service_breakdown'][0]['usage_count'],
            2,
        )
        self.assertEqual(response.context['sales_insights_scope_label'], 'All branches')

    def test_inventory_hero_stat_sums_stock_value_across_active_branches(self):
        admin = get_user_model().objects.create_superuser(
            username='inventory-value-admin',
            email='inventory-value-admin@example.com',
            password='A-secure-test-password-923!',
        )
        branches = [
            Branch.objects.create(
                name=f'Inventory Value Branch {index}',
                branch_code=f'IVB{index}',
                phone_number='09123456789',
                address='1 Clinic Street',
                city='Manila',
                state='NCR',
                zip_code='1000',
            )
            for index in range(1, 4)
        ]
        for index, branch in enumerate(branches, start=1):
            Product.objects.create(
                branch=branch,
                name=f'Inventory Test Product {index}',
                item_type='Product',
                price=20,
                unit_cost=10,
                stock_quantity=2,
            )
            Sale.objects.create(
                branch=branch,
                subtotal=100 * index,
                total=100 * index,
                status=Sale.Status.COMPLETED,
            )
        Sale.objects.create(
            branch=branches[0],
            subtotal=900,
            total=900,
            status=Sale.Status.VOIDED,
        )

        self.client.force_login(admin)
        response = self.client.get(reverse('accounts:admin_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_inventory_value'], 60)
        self.assertEqual(response.context['yearly_sales_revenue'], 600)
        self.assertEqual(
            response.context['dashboard_scope_label'], 'Across 3 Active Branches'
        )
        self.assertContains(response, 'Total Inventory Value')
        self.assertContains(response, 'Sales Revenue This Year')
        self.assertContains(response, 'Total User Accounts')
        self.assertContains(response, 'Across 3 Active Branches')
        self.assertNotContains(response, '0 low stock')
        self.assertNotContains(response, 'Month to date')
        self.assertContains(response, 'hero-stat-icon emerald')
        self.assertContains(response, 'bx-wallet')

    def test_inventory_hero_uses_current_stock_and_estimated_value_without_costs(self):
        admin = get_user_model().objects.create_superuser(
            username='inventory-estimate-admin',
            email='inventory-estimate-admin@example.com',
            password='A-secure-test-password-923!',
        )
        branch = Branch.objects.create(
            name='Inventory Estimate Branch',
            branch_code='IEB1',
            phone_number='09123456789',
            address='1 Clinic Street',
            city='Manila',
            state='NCR',
            zip_code='1000',
        )
        product = Product.objects.create(
            branch=branch,
            name='Inventory Estimate Product',
            item_type='Product',
            price=20,
            unit_cost=0,
            stock_quantity=4,
        )
        cancelled_product = Product.objects.create(
            branch=branch,
            name='Cancelled Inventory Product',
            item_type='Product',
            price=50,
            unit_cost=0,
            stock_quantity=2,
        )
        self.client.force_login(admin)

        response = self.client.get(reverse('accounts:admin_dashboard'))
        self.assertEqual(response.context['total_inventory_value'], 180)
        self.assertTrue(response.context['inventory_value_is_estimated'])

        StockAdjustment.objects.create(
            branch=branch,
            product=product,
            adjustment_type='REMOVE',
            date=timezone.localdate(),
            quantity=1,
            reason='Test stock reduction',
        )
        cancelled_product.delete()

        response = self.client.get(reverse('accounts:admin_dashboard'))
        self.assertEqual(response.context['total_inventory_value'], 60)
        self.assertTrue(response.context['inventory_value_is_estimated'])
        self.assertContains(response, 'Estimated at selling price')


class RolePermissionManagementTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username='rbac-test-admin',
            email='rbac-test-admin@example.com',
            password='A-secure-test-password-923!',
        )
        self.role = Role.objects.create(
            name='RBAC Editable Role',
            code='rbac-editable-role',
            hierarchy_level=4,
        )
        self.inventory, _ = Module.objects.get_or_create(
            code='inventory', defaults={'name': 'Inventory'},
        )
        self.transfers, _ = Module.objects.get_or_create(
            code='stock_transfers', defaults={'name': 'Stock Transfers'},
        )
        self.stock_monitor, _ = SpecialPermission.objects.get_or_create(
            code='can_access_stock_monitor',
            defaults={'name': 'Access Stock Monitor'},
        )

    def test_manage_grants_each_module_action(self):
        ModulePermission.objects.create(
            role=self.role,
            module=self.inventory,
            permission_type=ModulePermission.PermissionType.MANAGE,
        )

        for permission in ('VIEW', 'CREATE', 'EDIT', 'DELETE', 'MANAGE'):
            with self.subTest(permission=permission):
                self.assertTrue(
                    self.role.has_module_permission('inventory', permission)
                )

    def test_role_form_does_not_show_module_select_all_toggle(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse('accounts:role_create'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="perm_inventory_VIEW"')
        self.assertContains(response, 'name="perm_inventory_MANAGE"')
        self.assertNotContains(response, 'Select All for module')
        self.assertNotContains(response, 'all-perms-toggle')

    def test_role_edit_exposes_manage_and_preserves_hidden_permissions(self):
        ModulePermission.objects.create(
            role=self.role,
            module=self.transfers,
            permission_type=ModulePermission.PermissionType.VIEW,
        )
        self.client.force_login(self.admin)

        edit_url = reverse('accounts:role_edit', args=[self.role.pk])
        self.assertContains(self.client.get(edit_url), 'perm_inventory_MANAGE')

        response = self.client.post(edit_url, {
            'name': self.role.name,
            'description': self.role.description,
            'perm_inventory_MANAGE': 'on',
            'special_can_access_stock_monitor': 'on',
        })

        self.assertEqual(response.status_code, 302)
        self.role.refresh_from_db()
        self.assertTrue(self.role.has_module_permission('stock_transfers', 'VIEW'))
        self.assertTrue(self.role.has_module_permission('inventory', 'CREATE'))
        self.assertTrue(
            self.role.special_permissions.filter(permission=self.stock_monitor).exists()
        )

    def test_profile_updates_sync_appointments_and_customer_statements(self):
        branch = Branch.objects.create(
            name='Profile Sync Branch',
            phone_number='09123456789',
            address='1 Profile Street',
            city='Manila',
            state='NCR',
            zip_code='1000',
        )
        owner = get_user_model().objects.create_user(
            username='profile-sync-owner',
            first_name='Before',
            last_name='Profile',
            email='before@example.com',
            phone_number='09123456789',
            address='Old Address',
            password='A-secure-test-password-923!',
        )
        appointment = Appointment.objects.create(
            owner_name='Before Profile',
            owner_email=owner.email,
            owner_phone=owner.phone_number,
            owner_address=owner.address,
            pet_name='Profile Pet',
            branch=branch,
            appointment_date=timezone.localdate(),
            appointment_time=time(9, 0),
            user=owner,
            source=Appointment.Source.PORTAL,
        )
        statement = CustomerStatement.objects.create(
            patient_name='Profile Pet',
            owner_name='Before Profile',
            customer=owner,
            date=timezone.localdate(),
        )

        owner.first_name = 'After'
        owner.last_name = 'Updated'
        owner.email = 'after@example.com'
        owner.phone_number = '09987654321'
        owner.address = 'New Address'
        owner.save()

        appointment.refresh_from_db()
        statement.refresh_from_db()
        self.assertEqual(appointment.owner_name, 'After Updated')
        self.assertEqual(appointment.owner_email, 'after@example.com')
        self.assertEqual(appointment.owner_phone, '09987654321')
        self.assertEqual(appointment.owner_address, 'New Address')
        self.assertEqual(statement.owner_name, 'After Updated')

    def test_staff_account_profile_updates_sync_linked_staff_records(self):
        branch = Branch.objects.create(
            name='Staff Sync Branch',
            phone_number='09123456789',
            address='1 Staff Street',
            city='Manila',
            state='NCR',
            zip_code='1000',
        )
        staff_roles = (
            ('veterinarian', StaffMember.Position.VETERINARIAN),
            ('assistant_veterinarian', StaffMember.Position.VET_ASSISTANT),
            ('cashier', StaffMember.Position.RECEPTIONIST),
        )

        for role_code, position in staff_roles:
            with self.subTest(role_code=role_code):
                role, _ = Role.objects.get_or_create(
                    code=role_code,
                    defaults={
                        'name': role_code.replace('_', ' ').title(),
                        'hierarchy_level': 5,
                        'is_staff_role': True,
                    },
                )
                user = get_user_model().objects.create_user(
                    username=f'{role_code}-profile-sync',
                    first_name='Before',
                    last_name='Staff',
                    email=f'{role_code}@example.com',
                    phone_number='09123456789',
                    password='A-secure-test-password-923!',
                    assigned_role=role,
                    branch=branch,
                )
                staff = StaffMember.objects.create(
                    first_name=user.first_name,
                    last_name=user.last_name,
                    email=user.email,
                    phone=user.phone_number,
                    branch=branch,
                    position=position,
                    user=user,
                )

                user.first_name = 'After'
                user.last_name = 'Updated'
                user.email = f'updated-{role_code}@example.com'
                user.phone_number = '09987654321'
                user.branch = branch
                user.save()

                staff.refresh_from_db()
                self.assertEqual(staff.first_name, 'After')
                self.assertEqual(staff.last_name, 'Updated')
                self.assertEqual(staff.email, f'updated-{role_code}@example.com')
                self.assertEqual(staff.phone, '09987654321')
                self.assertEqual(staff.branch_id, branch.pk)

        admin = get_user_model().objects.create_superuser(
            username='admin-profile-sync',
            first_name='Before',
            last_name='Admin',
            email='admin@example.com',
            password='A-secure-test-password-923!',
        )
        admin.branch = branch
        admin.save()
        admin_staff = StaffMember.objects.create(
            first_name=admin.first_name,
            last_name=admin.last_name,
            email=admin.email,
            phone='',
            branch=branch,
            position=StaffMember.Position.ADMIN,
            user=admin,
        )

        admin.first_name = 'After'
        admin.last_name = 'Updated'
        admin.email = 'updated-admin@example.com'
        admin.phone_number = '09987654321'
        admin.save()

        admin_staff.refresh_from_db()
        self.assertEqual(admin_staff.first_name, 'After')
        self.assertEqual(admin_staff.last_name, 'Updated')
        self.assertEqual(admin_staff.email, 'updated-admin@example.com')
        self.assertEqual(admin_staff.phone, '09987654321')
        self.assertEqual(admin_staff.branch_id, branch.pk)

    def test_generic_audit_records_changed_fields_without_values(self):
        branch = Branch.objects.create(
            name='Audit Before',
            phone_number='09123456789',
            address='1 Audit Street',
            city='Test City',
            state='Test State',
            zip_code='1000',
        )
        token = set_current_actor(self.admin)
        try:
            branch.name = 'Audit After'
            branch.save(update_fields=['name'])
        finally:
            reset_current_actor(token)

        update_log = ActivityLog.objects.get(
            object_type='Branch',
            object_id=branch.pk,
            action_type=ActivityLog.ActionType.UPDATE,
        )
        self.assertIn('Changed fields: name', update_log.details)
        self.assertNotIn('Audit Before', update_log.details)
        self.assertNotIn('Audit After', update_log.details)

    def test_module_permission_creation_and_deletion_are_audited(self):
        token = set_current_actor(self.admin)
        try:
            permission = ModulePermission.objects.create(
                role=self.role,
                module=self.inventory,
                permission_type=ModulePermission.PermissionType.VIEW,
            )
            permission_id = permission.pk
            permission.delete()
        finally:
            reset_current_actor(token)

        permission_logs = ActivityLog.objects.filter(
            object_type='ModulePermission',
            object_id=permission_id,
        )
        self.assertTrue(permission_logs.filter(
            action_type=ActivityLog.ActionType.CREATE,
        ).exists())
        self.assertTrue(permission_logs.filter(
            action_type=ActivityLog.ActionType.DELETE,
        ).exists())


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class RegistrationEmailVerificationTests(TestCase):
    def registration_data(self, email):
        return {
            'username': 'newpetowner',
            'first_name': 'New',
            'last_name': 'Owner',
            'email': email,
            'phone_number': '09123456789',
            'address': '',
            'password1': 'A-secure-test-password-923!',
            'password2': 'A-secure-test-password-923!',
            'terms': 'on',
        }

    def test_registration_sends_verify_now_link_and_link_verifies_email(self):
        response = self.client.post(
            reverse('accounts:register_page'),
            self.registration_data('owner@example.com'),
        )

        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(username='newpetowner')
        self.assertFalse(user.email_verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['owner@example.com'])
        self.assertIn('Verify now', mail.outbox[0].alternatives[0][0])

        verification_url = re.search(r'https?://\S+', mail.outbox[0].body).group(0)
        token = parse_qs(urlsplit(verification_url).query)['token'][0]
        response = self.client.get(reverse('accounts:verify_email'), {'token': token})

        user.refresh_from_db()
        self.assertTrue(user.email_verified)
        self.assertEqual(response.status_code, 302)

    def test_registration_rejects_case_insensitive_duplicate_email(self):
        get_user_model().objects.create_user(
            username='existingowner',
            email='owner@example.com',
            password='A-secure-test-password-923!',
        )
        form = PetOwnerRegistrationForm(
            self.registration_data('OWNER@example.com')
        )

        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_profile_email_edit_checks_existing_addresses_case_insensitively(self):
        existing_user = get_user_model().objects.create_user(
            username='existingowner',
            email='owner@example.com',
            password='A-secure-test-password-923!',
        )
        editing_user = get_user_model().objects.create_user(
            username='editingowner',
            email='editing@example.com',
            password='A-secure-test-password-923!',
        )
        from .forms import UserProfileUpdateForm

        form = UserProfileUpdateForm(
            data={
                'username': editing_user.username,
                'first_name': '',
                'last_name': '',
                'email': existing_user.email.upper(),
                'phone_number': '',
                'address': '',
                'branch': '',
            },
            instance=editing_user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_new_users_are_unverified_by_default(self):
        user = get_user_model().objects.create_user(
            username='pendingowner',
            email='pending@example.com',
            password='A-secure-test-password-923!',
        )

        self.assertFalse(user.email_verified)

    def test_database_rejects_case_insensitive_duplicate_emails(self):
        get_user_model().objects.create_user(
            username='existingowner',
            email='owner@example.com',
            password='A-secure-test-password-923!',
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                get_user_model().objects.create_user(
                    username='duplicateowner',
                    email='OWNER@example.com',
                    password='A-secure-test-password-923!',
                )


class OwnerAccountDeactivationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='petowner',
            email='petowner@example.com',
            password='A-secure-test-password-923!',
        )

    def test_owner_has_one_month_to_cancel_by_logging_in(self):
        now = timezone.now()
        schedule_owner_deactivation(self.user, now=now)

        self.user.refresh_from_db()
        self.assertEqual(
            self.user.owner_deactivation_due_at,
            now + relativedelta(months=1),
        )
        self.assertEqual(resolve_owner_deactivation_on_login(self.user, now=now + relativedelta(days=2)), 'cancelled')

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertIsNone(self.user.owner_deactivation_due_at)

    def test_due_owner_is_deactivated_but_account_is_retained(self):
        now = timezone.now()
        self.user.owner_deactivation_requested_at = now - relativedelta(months=1)
        self.user.owner_deactivation_due_at = now - relativedelta(seconds=1)
        self.user.save(update_fields=[
            'owner_deactivation_requested_at',
            'owner_deactivation_due_at',
        ])

        self.assertEqual(expire_due_owner_accounts(now=now), 1)

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertEqual(self.user.owner_account_deactivated_at, now)
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())

    def test_overdue_login_expires_instead_of_cancelling(self):
        now = timezone.now()
        self.user.owner_deactivation_due_at = now - relativedelta(seconds=1)
        self.user.save(update_fields=['owner_deactivation_due_at'])

        self.assertEqual(resolve_owner_deactivation_on_login(self.user, now=now), 'expired')
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_profile_request_schedules_account_deactivation(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('accounts:request_owner_deactivation'),
            {'confirm_deactivation': 'on'},
        )

        self.user.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.user.is_active)
        self.assertIsNotNone(self.user.owner_deactivation_due_at)

    def test_pet_owner_login_before_due_date_cancels_schedule(self):
        schedule_owner_deactivation(self.user)

        response = self.client.post(reverse('accounts:login_page'), {
            'username': self.user.username,
            'password': 'A-secure-test-password-923!',
        })

        self.user.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.user.is_active)
        self.assertIsNone(self.user.owner_deactivation_due_at)

    def test_superadmin_archive_displays_retained_pet_and_medical_record(self):
        from patients.models import Pet
        from records.models import MedicalRecord

        now = timezone.now()
        self.user.is_active = False
        self.user.owner_account_deactivated_at = now
        self.user.save(update_fields=['is_active', 'owner_account_deactivated_at'])
        pet = Pet.objects.create(
            owner=self.user,
            name='Archive Companion',
            species='Dog',
            sex=Pet.Sex.MALE,
        )
        MedicalRecord.objects.bulk_create([
            MedicalRecord(pet=pet, date_recorded=now.date()),
        ])
        superadmin = get_user_model().objects.create_superuser(
            username='archiveadmin',
            email='archiveadmin@example.com',
            password='A-secure-test-password-923!',
        )
        self.client.force_login(superadmin)

        response = self.client.get(reverse('accounts:owner_archive'), {'q': 'Archive Companion'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pet Owner Archive')
        self.assertContains(response, 'Archive Companion')
        self.assertContains(response, 'Medical record')
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())


class BrowserLoginLockoutTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='loginowner',
            email='loginowner@example.com',
            password='A-secure-test-password-923!',
        )

    def test_five_failures_lock_only_the_current_browser(self):
        browser = Client()
        login_url = reverse('accounts:login_page')

        for _ in range(5):
            response = browser.post(login_url, {
                'username': self.user.username,
                'password': 'wrong-password',
            })
            self.assertEqual(response.status_code, 200)

        blocked_response = browser.post(login_url, {
            'username': self.user.username,
            'password': 'A-secure-test-password-923!',
        })
        self.assertEqual(blocked_response.status_code, 200)
        self.assertNotIn('_auth_user_id', browser.session)

        another_browser = Client()
        allowed_response = another_browser.post(login_url, {
            'username': self.user.username,
            'password': 'A-secure-test-password-923!',
        })
        self.assertEqual(allowed_response.status_code, 302)
        self.assertEqual(
            another_browser.session.get('_auth_user_id'), str(self.user.pk),
        )

    def test_locking_one_account_does_not_block_another_in_same_browser(self):
        second_user = get_user_model().objects.create_user(
            username='anotherloginowner',
            email='anotherloginowner@example.com',
            password='Another-secure-test-password-924!',
        )
        browser = Client()
        login_url = reverse('accounts:login_page')

        for _ in range(5):
            browser.post(login_url, {
                'username': self.user.username,
                'password': 'wrong-password',
            })

        response = browser.post(login_url, {
            'username': second_user.username,
            'password': 'Another-secure-test-password-924!',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            browser.session.get('_auth_user_id'), str(second_user.pk),
        )

    def test_first_browser_lock_expires_after_one_minute(self):
        from datetime import timedelta
        from unittest.mock import patch

        from django.utils import timezone

        now = timezone.now()
        browser = Client()
        login_url = reverse('accounts:login_page')

        with patch('accounts.views.timezone.now', return_value=now):
            for _ in range(5):
                browser.post(login_url, {
                    'username': self.user.username,
                    'password': 'wrong-password',
                })

        with patch(
            'accounts.views.timezone.now',
            return_value=now + timedelta(minutes=1, seconds=1),
        ):
            response = browser.post(login_url, {
                'username': self.user.username,
                'password': 'A-secure-test-password-923!',
            })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(browser.session.get('_auth_user_id'), str(self.user.pk))

    def test_lockout_increases_to_five_and_fifteen_minutes_then_caps(self):
        from datetime import timedelta
        from unittest.mock import patch

        from django.utils import timezone

        browser = Client()
        login_url = reverse('accounts:login_page')
        now = timezone.now()

        for expected_seconds in (60, 5 * 60, 15 * 60, 15 * 60):
            with patch('accounts.views.timezone.now', return_value=now):
                for _ in range(5):
                    response = browser.post(login_url, {
                        'username': self.user.username,
                        'password': 'wrong-password',
                    })
                    self.assertEqual(response.status_code, 200)

            lockout_state = next(iter(browser.session['login_lockouts'].values()))
            lock_until = lockout_state['locked_until']
            self.assertEqual(
                int(float(lock_until) - now.timestamp()),
                expected_seconds,
            )
            now += timedelta(seconds=expected_seconds + 1)

        with patch('accounts.views.timezone.now', return_value=now):
            response = browser.post(login_url, {
                'username': self.user.username,
                'password': 'A-secure-test-password-923!',
            })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(browser.session.get('login_lockouts'), {})