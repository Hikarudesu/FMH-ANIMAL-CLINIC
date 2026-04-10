"""
Forms for the inventory application.
"""
from django import forms
from django.utils import timezone
from FMHANIMALCLINIC.form_mixins import FormControlMixin
from .models import StockAdjustment, Product, StockTransfer


class ProductForm(FormControlMixin, forms.ModelForm):
    """Form for managing Product / Medication details."""
    class Meta:
        """Meta options for ProductForm."""
        model = Product
        fields = [
            'branch', 'item_type', 'name', 'description',
            'sku', 'barcode', 'manufacturer', 'unit_cost', 'price',
            'stock_quantity', 'min_stock_level', 'is_consumable',
            'expiration_date', 'is_available'
        ]
        widgets = {
            'branch': forms.Select(),
            'item_type': forms.Select(),
            'name': forms.TextInput(attrs={'placeholder': 'Item name'}),
            'description': forms.Textarea(attrs={'rows': 3}),
            'sku': forms.TextInput(attrs={'placeholder': 'Auto-generated if blank'}),
            'barcode': forms.TextInput(attrs={'placeholder': 'Scan or enter barcode'}),
            'manufacturer': forms.TextInput(attrs={'placeholder': 'e.g., Zoetis, Pfizer'}),
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
        super().__init__(*args, **kwargs)

        # Set today's date as default
        if not self.instance.pk:
            self.initial['date'] = timezone.now().date()

        # Filter products by branch if branch is selected
        if self.instance.pk and self.instance.branch:
            self.fields['product'].queryset = Product.objects.filter(
                branch=self.instance.branch,
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
        super().__init__(*args, **kwargs)
        if user_branch:
            # Only allow requesting TO the user's branch
            self.fields['destination_branch'].initial = user_branch
            self.fields['destination_branch'].disabled = True

            # Show products not in the user's branch
            self.fields['source_product'].queryset = Product.objects.exclude(
                branch=user_branch).filter(is_available=True)
