from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch

from accounts.rbac_models import Module, ModulePermission, Role
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

    def create_branch_restricted_user(self, branch):
        module, _ = Module.objects.get_or_create(
            code='inventory',
            defaults={'name': 'Inventory'},
        )
        role = Role.objects.create(
            name='Inventory Branch Role',
            code=f'inventory-branch-{branch.pk}',
            hierarchy_level=4,
            is_staff_role=True,
        )
        for permission in ('VIEW', 'CREATE', 'EDIT', 'DELETE'):
            ModulePermission.objects.create(
                role=role,
                module=module,
                permission_type=permission,
                restrict_to_branch=True,
            )
        return get_user_model().objects.create_user(
            username=f'inventory-user-{branch.pk}',
            email=f'inventory-user-{branch.pk}@example.com',
            password='A-secure-test-password-923!',
            branch=branch,
            assigned_role=role,
        )

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

    def test_restricted_user_registers_item_only_at_assigned_branch(self):
        other_branch = Branch.objects.create(
            name='Other Inventory Branch',
            phone_number='09123456789',
            address='2 Test Street',
            city='Test City',
            state='Test State',
            zip_code='1000',
        )
        user = self.create_branch_restricted_user(self.branch)
        self.client.force_login(user)

        response = self.client.post(
            reverse('inventory:product_new'),
            self.product_data(branch=str(other_branch.pk), name='Restricted Item'),
        )

        self.assertEqual(response.status_code, 302)
        product = Product.objects.get(name='Restricted Item')
        self.assertEqual(product.branch_id, self.branch.pk)

    def test_restricted_user_cannot_adjust_another_branch_product(self):
        other_branch = Branch.objects.create(
            name='Other Adjustment Branch',
            phone_number='09123456789',
            address='3 Test Street',
            city='Test City',
            state='Test State',
            zip_code='1000',
        )
        product = Product.objects.create(
            branch=other_branch,
            item_type=ProductForm().fields['item_type'].choices[0][0],
            name='Other Branch Item',
            unit_of_measurement=ProductForm().fields['unit_of_measurement'].choices[0][0],
            sale_type=ProductForm().fields['sale_type'].choices[0][0],
            price=20,
            stock_quantity=50,
        )
        user = self.create_branch_restricted_user(self.branch)
        self.client.force_login(user)

        form = StockAdjustmentForm(data={
            'branch': str(other_branch.pk),
            'product': str(product.pk),
            'adjustment_type': 'REMOVE',
            'quantity': '1',
            'reason': 'Should be rejected',
            'date': '2026-10-08',
        }, user=user)

        self.assertFalse(form.is_valid())
        self.assertIn('product', form.errors)

        response = self.client.get(
            reverse('inventory:get_branch_products', args=[other_branch.pk]),
        )
        self.assertEqual(response.status_code, 403)

    def test_restricted_user_without_branch_sees_no_branch_or_products(self):
        user = self.create_branch_restricted_user(self.branch)
        user.branch = None
        user.save(update_fields=['branch'])

        product_form = ProductForm(user=user)
        adjustment_form = StockAdjustmentForm(user=user)

        self.assertEqual(product_form.fields['branch'].queryset.count(), 0)
        self.assertEqual(adjustment_form.fields['branch'].queryset.count(), 0)
        self.assertEqual(adjustment_form.fields['product'].queryset.count(), 0)

    def test_non_superadmin_high_hierarchy_role_is_still_branch_restricted(self):
        other_branch = Branch.objects.create(
            name='Hierarchy Ten Other Branch',
            phone_number='09123456789',
            address='4 Test Street',
            city='Test City',
            state='Test State',
            zip_code='1000',
        )
        role = Role.objects.create(
            name='Non-superadmin Hierarchy Ten',
            code='non-superadmin-hierarchy-ten',
            hierarchy_level=10,
            is_staff_role=True,
        )
        user = get_user_model().objects.create_user(
            username='hierarchy-ten-inventory-user',
            email='hierarchy-ten-inventory-user@example.com',
            password='A-secure-test-password-923!',
            branch=self.branch,
            assigned_role=role,
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse('inventory:product_new'),
            self.product_data(branch=str(other_branch.pk), name='Hierarchy Restricted Item'),
        )

        self.assertEqual(response.status_code, 302)
        product = Product.objects.get(name='Hierarchy Restricted Item')
        self.assertEqual(product.branch_id, self.branch.pk)

    @patch(
        'inventory.forms.get_inventory_unit_choices',
        return_value=[('1 piece', '1 piece'), ('1 tablet', '1 tablet')],
    )
    def test_legacy_piece_unit_does_not_add_a_phantom_choice(self, _choices):
        form = ProductForm(instance=Product(unit_of_measurement='Piece'))

        self.assertEqual(
            list(form.fields['unit_of_measurement'].choices),
            [('1 piece', '1 piece'), ('1 tablet', '1 tablet')],
        )
        self.assertEqual(form.initial['unit_of_measurement'], '1 piece')

    @patch(
        'inventory.forms.get_inventory_unit_choices',
        return_value=[('1 piece', '1 piece'), ('1 tablet', '1 tablet')],
    )
    def test_removed_unit_is_not_reintroduced_when_editing_product(self, _choices):
        form = ProductForm(instance=Product(unit_of_measurement='1 old pack'))

        self.assertEqual(
            list(form.fields['unit_of_measurement'].choices),
            [('1 piece', '1 piece'), ('1 tablet', '1 tablet')],
        )
        self.assertEqual(form.initial['unit_of_measurement'], '1 piece')

    @patch(
        'inventory.forms.get_inventory_unit_choices',
        return_value=[('1 piece', '1 piece'), ('1 tablet', '1 tablet')],
    )
    def test_legacy_piece_value_uses_configured_unit_without_extra_option(self, _choices):
        form = ProductForm(instance=Product(unit_of_measurement='Piece'))

        self.assertEqual(
            list(form.fields['unit_of_measurement'].choices),
            [('1 piece', '1 piece'), ('1 tablet', '1 tablet')],
        )
        self.assertEqual(form.initial['unit_of_measurement'], '1 piece')