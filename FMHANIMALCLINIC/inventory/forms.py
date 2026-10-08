"""
Forms for the inventory application.
"""
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from FMHANIMALCLINIC.form_mixins import FormControlMixin
from branches.models import Branch
from .models import StockAdjustment, Product, StockTransfer
from settings.utils import (
    get_inventory_unit_choices,
    get_inventory_sale_type_choices,
    get_inventory_sale_type_value,
    get_inventory_sale_type_options,
)

from settings.utils import get_inventory_item_type_choices


def _user_branch(user):
    branch = getattr(user, 'branch', None)
    if branch:
        return branch
    staff_profile = getattr(user, 'staff_profile', None)
    return getattr(staff_profile, 'branch', None) if staff_profile else None


class ProductForm(FormControlMixin, forms.ModelForm):
    """Form for managing Product / Medication details."""

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        is_superadmin = bool(
            user and (
                user.is_superuser
                or getattr(getattr(user, 'assigned_role', None), 'code', None) == 'superadmin'
            )
        )
        if user and not is_superadmin:
            branch = _user_branch(user)
            self.fields['branch'].queryset = (
                Branch.objects.filter(pk=branch.pk)
                if branch else Branch.objects.none()
            )
            if branch:
                self.fields['branch'].initial = branch
                self.fields['branch'].disabled = True
        else:
            self.fields['branch'].queryset = Branch.objects.filter(is_active=True)

        self.fields['unit_of_measurement'].choices = get_inventory_unit_choices()
        self.fields['item_type'].choices = get_inventory_item_type_choices()
        self.fields['sale_type'].choices = get_inventory_sale_type_choices()

        # Map legacy unit spellings to the configured choice without exposing
        # units that Superadmin has removed from inventory settings.
        current_unit = getattr(self.instance, 'unit_of_measurement', '') or ''
        current_unit_key = current_unit.strip().casefold()
        legacy_unit_key = '1 piece' if current_unit_key in {'piece', 'per piece'} else current_unit_key
        matching_unit = next((
            value for value, _label in self.fields['unit_of_measurement'].choices
            if value.strip().casefold() in {current_unit_key, legacy_unit_key}
        ), None)
        if matching_unit:
            self.initial['unit_of_measurement'] = matching_unit
        elif current_unit and self.fields['unit_of_measurement'].choices:
            self.initial['unit_of_measurement'] = self.fields['unit_of_measurement'].choices[0][0]

        current_sale_type = getattr(self.instance, 'sale_type', '') or ''
        sale_type_choices = dict(self.fields['sale_type'].choices)
        if current_sale_type in {'piece', 'batch'}:
            available_values = list(sale_type_choices.keys())
            mapped_value = available_values[0] if current_sale_type == 'piece' else (
                available_values[1] if len(available_values) > 1 else available_values[0]
            )
            self.initial['sale_type'] = mapped_value
        elif current_sale_type and current_sale_type not in sale_type_choices:
            # Normalize legacy stored values (may contain underscores) to the
            # canonical slug form used by settings. This prevents duplicate
            # entries like 'per_piece' alongside 'per-piece'.
            normalized_key = get_inventory_sale_type_value(current_sale_type.replace('_', ' '))
            readable_label = current_sale_type.replace('_', ' ').title()

            if normalized_key not in sale_type_choices:
                self.fields['sale_type'].choices = [
                    *self.fields['sale_type'].choices,
                    (normalized_key, readable_label),
                ]

            self.initial['sale_type'] = normalized_key

    class Meta:
        """Meta options for ProductForm."""
        model = Product
        fields = [
            'branch', 'item_type', 'name', 'description',
            'sku', 'manufacturer', 'unit_of_measurement', 'sale_type',
            'unit_cost', 'price',
            'stock_quantity', 'min_stock_level', 'is_consumable',
            'expiration_date', 'is_available'
        ]
        widgets = {
            'branch': forms.Select(),
            'item_type': forms.Select(),
            'name': forms.TextInput(attrs={'placeholder': 'Item name'}),
            'description': forms.Textarea(attrs={'rows': 3}),
            'sku': forms.TextInput(attrs={'placeholder': 'Auto-generated if blank'}),
            'manufacturer': forms.TextInput(attrs={'placeholder': 'e.g., Zoetis, Pfizer'}),
            'unit_of_measurement': forms.Select(),
            'sale_type': forms.Select(),
            'unit_cost': forms.NumberInput(attrs={'step': '0.01', 'id': 'id_unit_cost'}),
            'price': forms.NumberInput(attrs={'step': '0.01', 'id': 'id_price'}),
            'stock_quantity': forms.NumberInput(),
            'min_stock_level': forms.NumberInput(),
            'expiration_date': forms.DateInput(attrs={'type': 'date'}),
            'is_available': forms.CheckboxInput(),
        }


class StockAdjustmentForm(FormControlMixin, forms.ModelForm):
    """
    Simplified stock adjustment form for Admins and Receptionists.

    Required fields: branch, product, adjustment_type, quantity, reason
    Optional fields: reference, cost_per_unit (hidden by default)
    """

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        is_superadmin = bool(
            user and (
                user.is_superuser
                or getattr(getattr(user, 'assigned_role', None), 'code', None) == 'superadmin'
            )
        )
        branch_restricted = bool(user and not is_superadmin)
        user_branch = _user_branch(user) if branch_restricted else None
        if branch_restricted:
            self.fields['branch'].queryset = (
                Branch.objects.filter(pk=user_branch.pk)
                if user_branch else Branch.objects.none()
            )
            if user_branch:
                self.fields['branch'].initial = user_branch
                self.fields['branch'].disabled = True
        else:
            self.fields['branch'].queryset = Branch.objects.filter(is_active=True)

        # Set today's date as default
        if not self.instance.pk:
            self.initial['date'] = timezone.now().date()

        if branch_restricted:
            selected_branch_id = user_branch.pk if user_branch else None
        else:
            selected_branch_id = self.data.get('branch')
        if not self.is_bound and self.instance.pk and self.instance.branch:
            selected_branch_id = self.instance.branch_id

        if branch_restricted and not user_branch:
            self.fields['product'].queryset = Product.objects.none()
        elif selected_branch_id:
            self.fields['product'].queryset = Product.objects.filter(
                branch_id=selected_branch_id,
                is_deleted=False
            ).order_by('name')
        else:
            self.fields['product'].queryset = Product.objects.filter(
                is_deleted=False
            ).order_by('name')

        # Only show user-facing adjustment types (exclude system types)
        self.fields['adjustment_type'].choices = StockAdjustment.ADJUSTMENT_TYPES

        # Make reference and cost_per_unit optional with better defaults
        self.fields['reference'].required = False
        self.fields['cost_per_unit'].required = False

        # Reason is required for manual adjustments
        self.fields['reason'].required = True

    def clean(self):
        cleaned_data = super().clean()
        adjustment_type = cleaned_data.get('adjustment_type')
        quantity = cleaned_data.get('quantity')
        product = cleaned_data.get('product')

        if quantity is not None and quantity < 1:
            self.add_error('quantity', 'Enter a quantity greater than zero.')
        elif (
            adjustment_type == 'REMOVE'
            and product
            and quantity is not None
            and quantity > product.stock_quantity
        ):
            self.add_error(
                'quantity',
                f'Cannot remove {quantity}; only {product.stock_quantity} '
                f'{product.unit_label} currently in stock.',
            )
        if product and cleaned_data.get('branch') and product.branch_id != cleaned_data['branch'].pk:
            self.add_error('product', 'The selected item does not belong to this branch.')

        return cleaned_data

    class Meta:
        """Meta options for StockAdjustmentForm."""
        model = StockAdjustment
        fields = ['branch', 'product', 'adjustment_type', 'quantity', 'reason',
                  'reference', 'date', 'cost_per_unit']
        widgets = {
            'branch': forms.Select(attrs={'id': 'id_branch'}),
            'product': forms.Select(attrs={'id': 'id_product'}),
            'adjustment_type': forms.Select(),
            'quantity': forms.NumberInput(attrs={'min': '1', 'placeholder': 'Enter quantity'}),
            'reason': forms.Textarea(attrs={
                'rows': 2,
                'placeholder': 'Describe why this adjustment is being made...'
            }),
            'reference': forms.TextInput(attrs={
                'placeholder': 'Optional: Receipt #, Invoice ID'
            }),
            'date': forms.DateInput(attrs={'type': 'date'}),
            'cost_per_unit': forms.NumberInput(attrs={
                'step': '0.01',
                'placeholder': '0.00'
            }),
        }


class StockTransferRequestForm(FormControlMixin, forms.ModelForm):
    """Form to request inventory from another branch."""
    class Meta:
        model = StockTransfer
        fields = ['source_product', 'destination_branch', 'quantity', 'notes']
        widgets = {
            'source_product': forms.Select(),
            'destination_branch': forms.Select(),
            'quantity': forms.NumberInput(attrs={'min': '1'}),
            'notes': forms.Textarea(attrs={
                'rows': 2,
                'placeholder': 'Reason for transfer...'
            }),
        }

    def __init__(self, *args, **kwargs):
        user_branch = kwargs.pop('user_branch', None)
        self.user_branch = user_branch
        super().__init__(*args, **kwargs)
        if user_branch:
            self.fields['destination_branch'].initial = user_branch
            self.fields['destination_branch'].widget = forms.HiddenInput()

            self.fields['source_product'].queryset = Product.objects.filter(
                branch__is_main_source=True,
                is_available=True,
            ).select_related('branch').order_by('name')

    def clean(self):
        cleaned_data = super().clean()
        source_product = cleaned_data.get('source_product')
        destination_branch = cleaned_data.get('destination_branch')

        if source_product and not source_product.branch.is_main_source:
            raise ValidationError({
                'source_product': 'Stock transfer requests must use the main source branch.'
            })

        if self.user_branch and destination_branch and destination_branch != self.user_branch:
            raise ValidationError({
                'destination_branch': 'Destination branch must match your assigned branch.'
            })

        return cleaned_data
