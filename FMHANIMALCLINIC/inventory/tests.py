from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch

from accounts.rbac_models import Module, ModulePermission, Role
from accounts.models import ActivityLog
from branches.models import Branch
from inventory.forms import ProductForm, StockAdjustmentForm
from inventory.models import Product, Reservation, StockAdjustment, StockTransfer
from settings.forms import InventorySettingsForm
from settings.utils import set_setting


@override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }
)
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
            'expiration_date': '',
            'is_available': 'on',
        }
        data.update(overrides)
        return data

    def test_allow_negative_stock_control_is_not_available(self):
        self.assertNotIn('allow_negative', InventorySettingsForm().fields)

    def test_stock_alert_toggle_is_not_available(self):
        self.assertNotIn('enable_alerts', InventorySettingsForm().fields)

    def test_management_type_filter_uses_configured_inventory_item_types(self):
        set_setting('inventory_item_type_options', ['Medical Supplies'])
        matching_product = Product.objects.create(
            branch=self.branch,
            item_type='Medical Supplies',
            name='Sterile Gauze',
            price=25,
            stock_quantity=8,
        )
        Product.objects.create(
            branch=self.branch,
            item_type='Medication',
            name='Hidden Medication',
            price=10,
            stock_quantity=4,
        )
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse('inventory:management'),
            {'type': 'Medical Supplies'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [option['value'] for option in response.context['status_filters'][0]['options']],
            ['Medical Supplies'],
        )
        self.assertEqual(
            [product.pk for product in response.context['products']],
            [matching_product.pk],
        )

    def create_branch_restricted_user(self, branch):
        module, _ = Module.objects.get_or_create(
            code='inventory',
            defaults={'name': 'Inventory'},
        )
        role = Role.objects.create(
            name='Inventory Branch Role',
            code=f'inventory-branch-{branch.pk}',
            hierarchy_level=2,
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

    def create_reservation_manager(self, branch):
        module, _ = Module.objects.get_or_create(
            code='reservations', defaults={'name': 'Reservations'},
        )
        role = Role.objects.create(
            name=f'Reservation Manager {branch.pk}',
            code=f'reservation-manager-{branch.pk}',
            hierarchy_level=2,
            is_staff_role=True,
        )
        for permission_type in (
            ModulePermission.PermissionType.EDIT,
            ModulePermission.PermissionType.DELETE,
        ):
            ModulePermission.objects.create(
                role=role,
                module=module,
                permission_type=permission_type,
                restrict_to_branch=True,
            )
        return get_user_model().objects.create_user(
            username=f'reservation-manager-{branch.pk}',
            password='A-secure-test-password-932!',
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

    def test_product_form_uses_global_threshold_instead_of_product_field(self):
        form = ProductForm()

        self.assertNotIn('min_stock_level', form.fields)

    @patch('inventory.models.get_inventory_low_stock_threshold', return_value=10)
    def test_product_status_uses_global_low_stock_threshold(self, _threshold):
        self.assertEqual(Product(stock_quantity=10).status, 'Low Stock')
        self.assertEqual(Product(stock_quantity=11).status, 'In Stock')

    def test_branchless_pet_owner_catalog_requires_a_preferred_branch(self):
        other_branch = Branch.objects.create(
            name='Second Catalog Branch',
            phone_number='09123456789',
            address='2 Test Street',
            city='Test City',
            state='Test State',
            zip_code='1000',
        )
        Product.objects.create(
            branch=self.branch, item_type='Product', name='First Branch Item', price=15,
        )
        Product.objects.create(
            branch=other_branch, item_type='Accessories', name='Second Branch Item', price=25,
        )
        owner = get_user_model().objects.create_user(
            username='catalog-owner', password='A-secure-test-password-923!',
        )
        self.client.force_login(owner)

        response = self.client.get(reverse('inventory:catalog'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['catalog_branch_assignment_required'])
        self.assertEqual(list(response.context['products']), [])
        self.assertFalse(response.context['show_all_branches'])
        self.assertContains(response, 'A branch assignment is required to view inventory.')

        response = self.client.get(
            reverse('inventory:catalog'), {'branch': str(other_branch.pk)},
        )
        self.assertEqual(list(response.context['products']), [])
        self.assertFalse(response.context['can_select_catalog_branch'])

    def test_branch_restricted_staff_cannot_select_another_catalog_branch(self):
        other_branch = Branch.objects.create(
            name='Restricted Catalog Other Branch',
            phone_number='09123456789',
            address='2 Test Street',
            city='Test City',
            state='Test State',
            zip_code='1000',
        )
        assigned_product = Product.objects.create(
            branch=self.branch, item_type='Product', name='Assigned Branch Item', price=15,
        )
        Product.objects.create(
            branch=other_branch, item_type='Product', name='Other Branch Catalog Item', price=25,
        )
        user = self.create_branch_restricted_user(self.branch)
        self.client.force_login(user)

        response = self.client.get(
            reverse('inventory:catalog'), {'branch': str(other_branch.pk)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['can_select_catalog_branch'])
        self.assertEqual(
            [product.pk for product in response.context['products']],
            [assigned_product.pk],
        )
        self.assertNotContains(response, 'Other Branch Catalog Item')

    def test_catalog_keeps_my_reservations_tab_after_refresh(self):
        reservation_product = Product.objects.create(
            branch=self.branch,
            item_type='Product',
            name='Catalog Reservation Item',
            price=20,
            stock_quantity=5,
        )
        Reservation.objects.create(
            user=self.admin,
            product=reservation_product,
            quantity=1,
            status=Reservation.Status.PENDING,
        )
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse('inventory:catalog'),
            {'tab': 'reservations'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['active_catalog_tab'], 'reservations')
        self.assertContains(
            response,
            'switchCatalogTab("reservations")',
        )

    def test_catalog_uses_modern_pagination_after_ten_products(self):
        for index in range(11):
            Product.objects.create(
                branch=self.branch,
                item_type='Product',
                name=f'Catalog Page Item {index}',
                price=20,
            )
        self.client.force_login(self.admin)

        first_page = self.client.get(
            reverse('inventory:catalog'),
            {'branch': str(self.branch.pk), 'tab': 'products'},
        )
        second_page = self.client.get(
            reverse('inventory:catalog'),
            {'branch': str(self.branch.pk), 'tab': 'products', 'page': 2},
        )

        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(first_page.context['page_obj'].paginator.per_page, 10)
        self.assertEqual(len(first_page.context['page_obj']), 10)
        self.assertContains(first_page, '?page=2&branch=' + str(self.branch.pk) + '&tab=products')
        self.assertEqual(second_page.context['page_obj'].number, 2)
        self.assertEqual(len(second_page.context['page_obj']), 1)

    @patch('inventory.views.get_inventory_low_stock_threshold', return_value=10)
    @patch('inventory.models.get_inventory_low_stock_threshold', return_value=10)
    def test_stock_monitor_uses_global_threshold_and_reports_shortfall(self, _model_threshold, _view_threshold):
        low_product = Product.objects.create(
            branch=self.branch,
            item_type='Product',
            name='Global Threshold Low Item',
            price=20,
            stock_quantity=8,
        )
        self.client.force_login(self.admin)

        response = self.client.get(reverse('inventory:super_admin_stock_monitoring'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['low_stock']), [low_product])
        self.assertEqual(response.context['low_stock'][0].stock_shortfall, 2)
        self.assertContains(response, '10 Piece')

    def test_branch_restricted_stock_monitor_status_filter_is_not_hidden_by_sidebar(self):
        user = self.create_branch_restricted_user(self.branch)
        stock_monitor_module, _ = Module.objects.get_or_create(
            code='stock_monitor',
            defaults={'name': 'Stock Monitor'},
        )
        ModulePermission.objects.create(
            role=user.assigned_role,
            module=stock_monitor_module,
            permission_type='VIEW',
            restrict_to_branch=True,
        )
        self.client.force_login(user)

        response = self.client.get(reverse('inventory:super_admin_stock_monitoring'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_branch_restricted'])
        self.assertContains(response, 'id="stockMonitorFilterBar"')
        self.assertContains(response, 'stock-monitor-status-filter')
        self.assertContains(response, 'right: auto !important')
        self.assertContains(response, 'z-index: 130')

    def test_branchless_restricted_staff_sees_assignment_notice_not_other_inventory(self):
        other_branch = Branch.objects.create(
            name='Unassigned Staff Other Branch',
            phone_number='09123456789',
            address='2 Test Street',
            city='Test City',
            state='Test State',
            zip_code='1000',
        )
        Product.objects.create(
            branch=other_branch,
            item_type='Product',
            name='Restricted Other Branch Item',
            price=20,
            stock_quantity=20,
        )
        user = self.create_branch_restricted_user(self.branch)
        user.branch = None
        user.save(update_fields=['branch'])
        self.client.force_login(user)

        response = self.client.get(reverse('inventory:management'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['branch_assignment_required'])
        self.assertEqual(response.context['products'].paginator.count, 0)
        self.assertContains(response, 'Ask an administrator to assign your branch')
        self.assertNotContains(response, 'Restricted Other Branch Item')

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
            name='Hierarchy Five Other Branch',
            phone_number='09123456789',
            address='4 Test Street',
            city='Test City',
            state='Test State',
            zip_code='1000',
        )
        role = Role.objects.create(
            name='Non-superadmin Hierarchy Five',
            code='non-superadmin-hierarchy-five',
            hierarchy_level=5,
            is_staff_role=True,
        )
        user = get_user_model().objects.create_user(
            username='hierarchy-five-inventory-user',
            email='hierarchy-five-inventory-user@example.com',
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

    def test_stock_monitor_in_stock_filter_returns_matching_products(self):
        in_stock = Product.objects.create(
            branch=self.branch,
            item_type='Product',
            name='Adequately Stocked Item',
            price=20,
            stock_quantity=11,
        )
        Product.objects.create(
            branch=self.branch,
            item_type='Product',
            name='Low Stock Item',
            price=20,
            stock_quantity=2,
        )
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse('inventory:super_admin_stock_monitoring'),
            {'status': 'In Stock'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['in_stock']), [in_stock])
        self.assertEqual(response.context['low_stock'], [])
        self.assertContains(response, 'Adequately Stocked Item')
        self.assertNotContains(response, '>Low Stock Item</td>')

    def test_soft_deleted_product_is_logged_as_delete_with_snapshot(self):
        product = Product.objects.create(
            branch=self.branch,
            item_type='Product',
            name='Deleted Stock Item',
            sku='DEL-001',
            price=20,
            stock_quantity=4,
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('inventory:product_delete', args=[product.pk]),
        )

        self.assertEqual(response.status_code, 302)
        deletion_log = ActivityLog.objects.get(
            action_type=ActivityLog.ActionType.DELETE,
            object_type='Product',
            object_id=product.pk,
        )
        self.assertIn('Deleted Stock Item', deletion_log.action)
        self.assertIn('DEL-001', deletion_log.details)
        self.assertIn('Stock: 4', deletion_log.details)
        self.assertEqual(deletion_log.ip_address, '127.0.0.1')

    def test_product_with_pending_reservation_cannot_be_deleted(self):
        product = Product.objects.create(
            branch=self.branch,
            item_type='Product',
            name='Reserved Item',
            price=20,
        )
        Reservation.objects.create(
            user=self.admin,
            product=product,
            status=Reservation.Status.PENDING,
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('inventory:product_delete', args=[product.pk]),
        )

        self.assertEqual(response.status_code, 302)
        product.refresh_from_db()
        self.assertFalse(product.is_deleted)
        self.assertContains(
            self.client.get(reverse('inventory:management')),
            'pending reservations',
        )

    def test_product_can_be_deleted_after_reservation_is_released(self):
        product = Product.objects.create(
            branch=self.branch,
            item_type='Product',
            name='Completed Reservation Item',
            price=20,
        )
        Reservation.objects.create(
            user=self.admin,
            product=product,
            status=Reservation.Status.RELEASED,
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('inventory:product_delete', args=[product.pk]),
        )

        self.assertEqual(response.status_code, 302)
        product.refresh_from_db()
        self.assertTrue(product.is_deleted)

    def test_branch_staff_delete_button_is_disabled_for_pending_reservation(self):
        product = Product.objects.create(
            branch=self.branch,
            item_type='Product',
            name='Branch Reserved Item',
            price=20,
        )
        Reservation.objects.create(
            user=self.admin,
            product=product,
            status=Reservation.Status.PENDING,
        )
        receptionist = self.create_branch_restricted_user(self.branch)
        self.client.force_login(receptionist)

        response = self.client.get(reverse('inventory:management'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cannot delete: this item has pending reservations')
        self.assertContains(response, 'disabled aria-disabled="true"')

    def test_reservation_actions_cannot_target_another_branch_by_id(self):
        other_branch = Branch.objects.create(
            name='Foreign Reservation Branch',
            phone_number='09123456780',
            address='2 Test Street',
            city='Test City',
            state='Test State',
            zip_code='1001',
        )
        product = Product.objects.create(
            branch=other_branch,
            item_type='Product',
            name='Foreign Reserved Item',
            price=20,
            stock_quantity=5,
        )
        reservation = Reservation.objects.create(
            user=self.admin,
            product=product,
            quantity=2,
            status=Reservation.Status.PENDING,
        )
        staff = self.create_reservation_manager(self.branch)
        self.client.force_login(staff)

        confirm_response = self.client.post(
            reverse('inventory:confirm_reservation', args=[reservation.pk]),
        )
        cancel_response = self.client.post(
            reverse('inventory:cancel_reservation', args=[reservation.pk]),
        )

        self.assertEqual(confirm_response.status_code, 404)
        self.assertEqual(cancel_response.status_code, 404)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.PENDING)
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 5)

    def test_reservation_confirmation_and_cancellation_require_post(self):
        product = Product.objects.create(
            branch=self.branch,
            item_type='Product',
            name='GET Guard Reservation Item',
            price=20,
            stock_quantity=5,
        )
        reservation = Reservation.objects.create(
            user=self.admin,
            product=product,
            quantity=2,
            status=Reservation.Status.PENDING,
        )
        staff = self.create_reservation_manager(self.branch)
        self.client.force_login(staff)

        confirm_response = self.client.get(
            reverse('inventory:confirm_reservation', args=[reservation.pk]),
        )
        cancel_response = self.client.get(
            reverse('inventory:cancel_reservation', args=[reservation.pk]),
        )

        self.assertEqual(confirm_response.status_code, 405)
        self.assertEqual(cancel_response.status_code, 405)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.PENDING)

    def test_cancelling_reservation_returns_to_reservations_tab(self):
        product = Product.objects.create(
            branch=self.branch,
            item_type='Product',
            name='Cancelled Reservation Item',
            price=20,
            stock_quantity=5,
        )
        reservation = Reservation.objects.create(
            user=self.admin,
            product=product,
            quantity=2,
            status=Reservation.Status.PENDING,
        )
        staff = self.create_reservation_manager(self.branch)
        self.client.force_login(staff)

        response = self.client.post(
            reverse('inventory:cancel_reservation', args=[reservation.pk]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"{reverse('inventory:management')}?tab=reservations")
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CANCELLED)

    def test_confirming_reservation_uses_explicit_pos_checkout_route(self):
        product = Product.objects.create(
            branch=self.branch,
            item_type='Product',
            name='POS Redirect Item',
            price=20,
            stock_quantity=5,
        )
        reservation = Reservation.objects.create(
            user=self.admin,
            product=product,
            quantity=1,
            status=Reservation.Status.PENDING,
        )
        manager = self.create_reservation_manager(self.branch)
        self.client.force_login(manager)

        response = self.client.post(
            reverse('inventory:confirm_reservation', args=[reservation.pk]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            f"{reverse('pos:checkout_alt')}?reservation={reservation.pk}",
        )

    def test_pending_reservation_quantity_syncs_inventory(self):
        product = Product.objects.create(
            branch=self.branch,
            item_type='Product',
            name='Adjustable Reserved Item',
            price=20,
            stock_quantity=8,
        )
        reservation = Reservation.objects.create(
            user=self.admin,
            product=product,
            quantity=2,
            status=Reservation.Status.PENDING,
        )
        self.client.force_login(self.admin)

        increase_response = self.client.post(
            reverse('inventory:update_reservation_quantity', args=[reservation.pk]),
            {'quantity': 3},
        )

        self.assertEqual(increase_response.status_code, 200)
        reservation.refresh_from_db()
        product.refresh_from_db()
        self.assertEqual(reservation.quantity, 3)
        self.assertEqual(product.stock_quantity, 7)
        self.assertEqual(
            StockAdjustment.objects.filter(
                reference=f'RSV-{reservation.pk}-QTY',
                adjustment_type='REMOVE',
            ).count(),
            1,
        )

        decrease_response = self.client.post(
            reverse('inventory:update_reservation_quantity', args=[reservation.pk]),
            {'quantity': 1},
        )

        self.assertEqual(decrease_response.status_code, 200)
        reservation.refresh_from_db()
        product.refresh_from_db()
        self.assertEqual(reservation.quantity, 1)
        self.assertEqual(product.stock_quantity, 9)

    def test_stock_adjustment_reaching_zero_marks_item_unavailable(self):
        product = Product.objects.create(
            branch=self.branch,
            item_type='Product',
            name='Last Stock Item',
            price=20,
            stock_quantity=3,
            is_available=True,
        )

        StockAdjustment.objects.create(
            branch=self.branch,
            product=product,
            adjustment_type='REMOVE',
            date='2026-10-08',
            quantity=3,
            reason='Sold out',
        )

        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 0)
        self.assertFalse(product.is_available)

    def test_stock_adjustment_cannot_remove_more_than_available(self):
        product = Product.objects.create(
            branch=self.branch,
            item_type='Product',
            name='Limited Stock Item',
            price=20,
            stock_quantity=3,
            is_available=True,
        )

        with self.assertRaises(ValidationError):
            StockAdjustment.objects.create(
                branch=self.branch,
                product=product,
                adjustment_type='REMOVE',
                date='2026-10-08',
                quantity=4,
                reason='Attempted overdraw',
            )

        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 3)
        self.assertFalse(
            StockAdjustment.objects.filter(product=product).exists()
        )

    def test_superadmin_can_open_and_approve_transfer_from_source_branch(self):
        self.branch.is_main_source = True
        self.branch.save(update_fields=['is_main_source'])
        self.admin.branch = self.branch
        self.admin.save(update_fields=['branch'])
        destination = Branch.objects.create(
            name='Transfer Destination Branch',
            phone_number='09123456789',
            address='2 Test Street',
            city='Test City',
            state='Test State',
            zip_code='1000',
        )
        product = Product.objects.create(
            branch=self.branch,
            item_type='Product',
            name='Transfer Item',
            price=20,
            stock_quantity=8,
        )
        transfer = StockTransfer.objects.create(
            source_product=product,
            destination_branch=destination,
            requested_by=self.admin,
            quantity=2,
            notes='Branch restock request',
        )
        self.client.force_login(self.admin)

        listing = self.client.get(reverse('inventory:transfer_list'))
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, 'Approve')
        self.assertContains(listing, 'Stock Transfer')
        self.assertNotContains(listing, '>Request Transfer<')

        response = self.client.post(
            reverse('inventory:transfer_update_status', args=[transfer.pk]),
            {'action': 'approve'},
        )

        self.assertEqual(response.status_code, 302)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, StockTransfer.Status.APPROVED)
        approval_log = ActivityLog.objects.get(
            object_type='StockTransfer',
            object_id=transfer.pk,
            action_type=ActivityLog.ActionType.APPROVE,
        )
        self.assertIn('Branch restock request', approval_log.details)

    def test_transfer_receipt_adds_stock_to_existing_destination_product(self):
        destination = Branch.objects.create(
            name='Existing Product Destination',
            phone_number='09123456780',
            address='2 Test Street',
            city='Test City',
            state='Test State',
            zip_code='1001',
        )
        source_product = Product.objects.create(
            branch=self.branch,
            item_type='Product',
            name='Shared Transfer Product',
            manufacturer='Test Manufacturer',
            sku='SOURCE-SKU',
            price=20,
            stock_quantity=8,
        )
        destination_product = Product.objects.create(
            branch=destination,
            item_type='Product',
            name='Shared Transfer Product',
            manufacturer='Test Manufacturer',
            sku='DESTINATION-SKU',
            price=20,
            stock_quantity=5,
        )
        transfer = StockTransfer.objects.create(
            source_product=source_product,
            destination_branch=destination,
            requested_by=self.admin,
            quantity=2,
            status=StockTransfer.Status.APPROVED,
        )

        transfer.complete_transfer(self.admin)

        destination_product.refresh_from_db()
        source_product.refresh_from_db()
        self.assertEqual(destination_product.stock_quantity, 7)
        self.assertEqual(source_product.stock_quantity, 6)
        self.assertEqual(
            Product.objects.filter(branch=destination, name='Shared Transfer Product').count(),
            1,
        )
        self.assertTrue(
            StockAdjustment.objects.filter(
                product=destination_product,
                adjustment_type='TRANSFER_IN',
                quantity=2,
            ).exists()
        )

    def test_pending_transfer_cannot_move_stock_before_recipient_receives_it(self):
        destination = Branch.objects.create(
            name='Pending Transfer Destination',
            phone_number='09123456780',
            address='2 Test Street',
            city='Test City',
            state='Test State',
            zip_code='1001',
        )
        source_product = Product.objects.create(
            branch=self.branch,
            item_type='Product',
            name='Pending Transfer Product',
            price=20,
            stock_quantity=8,
        )
        transfer = StockTransfer.objects.create(
            source_product=source_product,
            destination_branch=destination,
            requested_by=self.admin,
            quantity=2,
        )

        with self.assertRaisesMessage(ValueError, 'must be approved'):
            transfer.complete_transfer(self.admin)

        source_product.refresh_from_db()
        self.assertEqual(source_product.stock_quantity, 8)
        self.assertFalse(
            Product.objects.filter(branch=destination).exists()
        )
        self.assertFalse(
            StockAdjustment.objects.filter(
                adjustment_type__in=['TRANSFER_IN', 'TRANSFER_OUT'],
            ).exists()
        )

    def test_inventory_search_filters_products_before_pagination(self):
        older_product = Product.objects.create(
            branch=self.branch,
            item_type='Product',
            name='Search Result Beyond First Page',
            price=20,
        )
        Product.objects.filter(pk=older_product.pk).update(
            created_at='2020-01-01T00:00:00Z'
        )
        for index in range(20):
            Product.objects.create(
                branch=self.branch,
                item_type='Product',
                name=f'Unrelated Inventory Item {index}',
                price=20,
            )
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse('inventory:management'),
            {'q': 'Search Result Beyond First Page'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [product.pk for product in response.context['products']],
            [older_product.pk],
        )
        self.assertEqual(response.context['products'].paginator.count, 1)

    def test_inventory_items_and_movements_paginate_independently(self):
        for index in range(21):
            product = Product.objects.create(
                branch=self.branch,
                item_type='Product',
                name=f'Pagination Item {index}',
                price=20,
                stock_quantity=1,
            )
            StockAdjustment.objects.create(
                branch=self.branch,
                product=product,
                adjustment_type='ADD',
                date=timezone.localdate(),
                quantity=1,
                reason='Pagination test movement',
            )
        self.client.force_login(self.admin)

        items_page_response = self.client.get(
            reverse('inventory:management'),
            {'items_page': 2},
        )
        self.assertEqual(items_page_response.status_code, 200)
        self.assertEqual(items_page_response.context['products'].number, 2)
        self.assertEqual(items_page_response.context['adjustments'].number, 1)
        self.assertContains(items_page_response, '?items_page=1')
        self.assertContains(items_page_response, '?movements_page=2&items_page=2')

        movements_page_response = self.client.get(
            reverse('inventory:management'),
            {'movements_page': 2},
        )
        self.assertEqual(movements_page_response.status_code, 200)
        self.assertEqual(movements_page_response.context['products'].number, 1)
        self.assertEqual(movements_page_response.context['adjustments'].number, 2)
        self.assertContains(movements_page_response, '?items_page=2&movements_page=2')

    def test_inventory_movement_filter_keeps_movements_tab_active(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse('inventory:management'),
            {'tab': 'movements', 'type': 'Product'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['active_inventory_tab'], 'movements')
        self.assertContains(
            response,
            '<input type="hidden" name="tab" value="movements">',
        )
        self.assertContains(response, "|| 'movements'")

    def test_inventory_tabs_render_active_section_after_refresh(self):
        self.client.force_login(self.admin)

        movements_response = self.client.get(
            reverse('inventory:management'),
            {'tab': 'movements'},
        )
        self.assertContains(
            movements_response,
            '<div id="inv-movements-section" class="inv-section active" style="">',
            html=False,
        )
        self.assertContains(
            movements_response,
            '<div id="inv-items-section" class="inv-section" style="display: none;">',
            html=False,
        )

    def test_superadmin_cannot_create_a_stock_transfer_request(self):
        self.admin.branch = self.branch
        self.admin.save(update_fields=['branch'])
        self.client.force_login(self.admin)

        listing = self.client.get(reverse('inventory:transfer_list'))
        response = self.client.get(reverse('inventory:transfer_request'))

        self.assertNotContains(listing, '>Request Transfer<')
        self.assertRedirects(response, reverse('inventory:transfer_list'))
        self.assertEqual(StockTransfer.objects.count(), 0)

    def test_stock_movement_table_shows_branch_unit_and_timestamps(self):
        product = Product.objects.create(
            branch=self.branch,
            item_type='Product',
            name='Movement Detail Item',
            price=20,
            stock_quantity=0,
        )
        StockAdjustment.objects.create(
            branch=self.branch,
            product=product,
            adjustment_type='ADD',
            reference='PO-1001',
            date='2026-10-08',
            quantity=5,
            reason='New shipment received',
        )
        self.client.force_login(self.admin)

        response = self.client.get(reverse('inventory:management'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Recorded At')
        self.assertContains(response, 'Movement Detail Item')
        self.assertContains(response, 'PO-1001')
        self.assertContains(response, 'Inventory Test Branch')

    def test_activity_logs_use_server_pagination_and_two_step_clear_confirmation(self):
        for index in range(55):
            ActivityLog.objects.create(
                user=self.admin,
                action=f'Activity log pagination {index}',
                category=ActivityLog.Category.SYSTEM,
            )
        self.client.force_login(self.admin)

        response = self.client.get(reverse('inventory:activity_logs'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context['page_obj'].paginator.count,
            ActivityLog.objects.count(),
        )
        self.assertEqual(len(response.context['logs']), 50)
        self.assertEqual(response.content.decode().count('class="log-card category-'), 50)
        self.assertContains(response, 'id="continueClearActivityLogsBtn"')
        self.assertContains(response, 'id="finalClearModal"')
        self.assertContains(response, 'This is the final warning.')

    def test_activity_log_filters_fetch_matching_data_across_system(self):
        other_branch = Branch.objects.create(
            name='Other Activity Log Branch',
            phone_number='09123456780',
            address='2 Test Street',
            city='Test City',
            state='Test State',
            zip_code='1001',
        )
        other_user = get_user_model().objects.create_user(
            username='activity-log-filter-user',
            email='activity-log-filter-user@example.com',
            password='A-secure-test-password-923!',
        )
        matching_log = ActivityLog.objects.create(
            user=other_user,
            action='Created a POS transaction',
            category=ActivityLog.Category.POS,
            action_type=ActivityLog.ActionType.CREATE,
            branch=other_branch,
        )
        ActivityLog.objects.create(
            user=self.admin,
            action='Updated inventory',
            category=ActivityLog.Category.STOCK,
            action_type=ActivityLog.ActionType.UPDATE,
            branch=self.branch,
        )
        old_log = ActivityLog.objects.create(
            user=other_user,
            action='Older POS transaction',
            category=ActivityLog.Category.POS,
            action_type=ActivityLog.ActionType.CREATE,
            branch=other_branch,
        )
        ActivityLog.objects.filter(pk=old_log.pk).update(
            timestamp=timezone.now() - timedelta(days=2),
        )
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse('inventory:activity_logs'),
            {
                'branch_id': other_branch.pk,
                'category': ActivityLog.Category.POS,
                'user_id': other_user.pk,
                'action_type': ActivityLog.ActionType.CREATE,
                'date_filter': 'today',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [log.pk for _group, logs in response.context['grouped_logs'] for log in logs],
            [matching_log.pk],
        )
        self.assertContains(response, 'name="user_id"')
        self.assertContains(response, f'value="{other_user.pk}" selected')

    def test_clear_activity_logs_deletes_only_selected_logs(self):
        ActivityLog.objects.create(
            user=self.admin,
            action='POS log to clear',
            category=ActivityLog.Category.POS,
        )
        ActivityLog.objects.create(
            user=self.admin,
            action='System log to keep',
            category=ActivityLog.Category.SYSTEM,
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('inventory:clear_activity_logs'),
            {
                'date_filter': 'all',
                'branch_id': '',
                'category': ActivityLog.Category.POS,
                'user_id': '',
                'action_type': 'all',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            ActivityLog.objects.filter(category=ActivityLog.Category.POS).exists()
        )
        self.assertTrue(
            ActivityLog.objects.filter(category=ActivityLog.Category.SYSTEM).exists()
        )

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