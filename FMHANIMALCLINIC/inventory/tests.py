from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from branches.models import Branch
from inventory.forms import ProductForm, StockAdjustmentForm
from inventory.models import Product, StockAdjustment


class InventoryWorkflowTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name='Inventory Test Branch',
            phone_number='09123456789',
            address='1 Test Street',
            city='Test City',
            state='Test State',
            zip_code='1000',
        )
        self.admin = get_user_model().objects.create_superuser(
            username='inventory-test-admin',
            email='inventory-test-admin@example.com',
            password='A-secure-test-password-923!',
        )

    def product_data(self, **overrides):
        form = ProductForm()
        data = {
            'branch': str(self.branch.pk),
            'item_type': form.fields['item_type'].choices[0][0],
            'name': 'Test Medicine',
            'description': '',
            'sku': '',
            'manufacturer': '',
            'unit_of_measurement': form.fields['unit_of_measurement'].choices[0][0],
            'sale_type': form.fields['sale_type'].choices[0][0],
            'unit_cost': '10.00',
            'price': '20.00',
            'stock_quantity': '50',
            'min_stock_level': '5',
            'expiration_date': '',
            'is_available': 'on',
        }
        data.update(overrides)
        return data

    def test_new_item_initial_stock_is_recorded_once(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('inventory:product_new'),
            self.product_data(),
        )

        self.assertEqual(response.status_code, 302)
        product = Product.objects.get(name='Test Medicine')
        self.assertEqual(product.stock_quantity, 50)
        self.assertTrue(product.is_available)
        self.assertEqual(
            StockAdjustment.objects.filter(product=product).count(), 1,
        )

    def test_product_can_remain_unavailable_with_positive_stock(self):
        product_form = ProductForm(data=self.product_data(is_available=''))

        self.assertTrue(product_form.is_valid(), product_form.errors)
        product = product_form.save()

        self.assertEqual(product.stock_quantity, 50)
        self.assertFalse(product.is_available)

    def test_removing_more_than_available_stock_shows_warning_without_adjustment(self):
        product = Product.objects.create(
            branch=self.branch,
            item_type=ProductForm().fields['item_type'].choices[0][0],
            name='Limited Stock Medicine',
            unit_of_measurement=ProductForm().fields['unit_of_measurement'].choices[0][0],
            sale_type=ProductForm().fields['sale_type'].choices[0][0],
            price=20,
            stock_quantity=50,
        )
        self.client.force_login(self.admin)

        response = self.client.post(reverse('inventory:adjustment_new'), {
            'branch': str(self.branch.pk),
            'product': str(product.pk),
            'adjustment_type': 'REMOVE',
            'quantity': '100',
            'reason': 'Test over-removal',
            'reference': '',
            'date': '2026-10-08',
            'cost_per_unit': '',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cannot remove 100')
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 50)
        self.assertFalse(StockAdjustment.objects.filter(product=product).exists())