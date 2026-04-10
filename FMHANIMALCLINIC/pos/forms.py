"""Forms for POS module."""

from decimal import Decimal

from django import forms
from django.db.models import Q

from FMHANIMALCLINIC.form_mixins import AdminInputMixin, validate_philippines_phone
from billing.models import Service
from inventory.models import Product
from patients.models import Pet
from accounts.models import User

from .models import Sale, SaleItem, Payment, Refund


class SaleForm(AdminInputMixin, forms.ModelForm):
    """Form for creating/editing a sale."""

    class Meta:
        model = Sale
        fields = [
            'customer_type', 'customer', 'pet',
            'guest_name', 'guest_phone', 'guest_email',
            'discount_percent', 'discount_reason', 'notes'
        ]
        widgets = {
            'customer_type': forms.Select(),
            'customer': forms.Select(attrs={'data-search': 'true'}),
            'pet': forms.Select(attrs={'data-search': 'true'}),
            'guest_name': forms.TextInput(attrs={'placeholder': 'Customer name'}),
            'guest_phone': forms.TextInput(attrs={
                'placeholder': '09XXXXXXXXX',
                'inputmode': 'numeric',
                'pattern': '[0-9]{11}',
                'minlength': '11',
                'maxlength': '11',
                'oninput': "this.value=this.value.replace(/\\D/g,'')",
            }),
            'guest_email': forms.EmailInput(attrs={'placeholder': 'email@example.com'}),
            'discount_percent': forms.NumberInput(attrs={
                'placeholder': '0',
                'step': '0.01',
                'min': '0',
                'max': '100'
            }),
            'discount_reason': forms.TextInput(attrs={'placeholder': 'Reason for discount (required if discount applied)'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Additional notes'}),
        }

    def __init__(self, *args, branch=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Make customer and pet optional
        self.fields['customer'].required = False
        self.fields['pet'].required = False

        # Filter customers to pet owners (not staff or no role)
        self.fields['customer'].queryset = User.objects.filter(
            is_active=True
        ).filter(
            Q(assigned_role__is_staff_role=False) | Q(assigned_role__isnull=True)
        ).order_by('first_name', 'last_name')

        # Filter pets
        if branch:
            self.fields['pet'].queryset = Pet.objects.filter(
                is_active=True
            ).order_by('name')
        else:
            self.fields['pet'].queryset = Pet.objects.filter(
                is_active=True
            ).order_by('name')

    def clean_guest_phone(self):
        return validate_philippines_phone(self.cleaned_data.get('guest_phone', ''))

    def clean(self):
        """Validate that discount_reason is provided when discount_percent > 0."""
        cleaned_data = super().clean()
        discount_percent = cleaned_data.get('discount_percent') or Decimal('0')
        discount_reason = cleaned_data.get('discount_reason', '').strip()

        if discount_percent > 0 and not discount_reason:
            raise forms.ValidationError({
                'discount_reason': 'Discount reason is required when applying a discount.'
            })

        return cleaned_data


class SaleItemForm(forms.Form):
    """Form for adding items to a sale."""

    item_type = forms.ChoiceField(choices=SaleItem.ItemType.choices)
    item_id = forms.IntegerField()
    quantity = forms.IntegerField(min_value=1, initial=1)
    discount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        initial=Decimal('0.00'),
        required=False
    )

    def __init__(self, *args, branch=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.branch = branch

    def clean(self):
        cleaned_data = super().clean()
        item_type = cleaned_data.get('item_type')
        item_id = cleaned_data.get('item_id')
        quantity = cleaned_data.get('quantity', 1)

        if item_type == SaleItem.ItemType.SERVICE:
            try:
                item = Service.objects.get(pk=item_id, active=True)
                cleaned_data['item'] = item
                cleaned_data['name'] = item.name
                cleaned_data['unit_price'] = item.price
            except Service.DoesNotExist:
                raise forms.ValidationError("Service not found.")

        elif item_type in [SaleItem.ItemType.PRODUCT, SaleItem.ItemType.MEDICATION]:
            try:
                item = Product.objects.get(pk=item_id, is_available=True)
                if item.stock_quantity < quantity:
                    raise forms.ValidationError(
                        f"Insufficient stock. Available: {item.stock_quantity}"
                    )
                cleaned_data['item'] = item
                cleaned_data['name'] = item.name
                cleaned_data['unit_price'] = item.price
            except Product.DoesNotExist:
                raise forms.ValidationError("Product not found.")

        return cleaned_data


class PaymentForm(AdminInputMixin, forms.ModelForm):
    """Form for recording a payment."""

    class Meta:
        model = Payment
        fields = ['method', 'amount', 'reference_number', 'notes']
        widgets = {
            'method': forms.Select(),
            'amount': forms.NumberInput(attrs={
                'placeholder': '0.00',
                'step': '0.01',
                'min': '0.01'
            }),
            'reference_number': forms.TextInput(attrs={
                'placeholder': 'Reference # (for card/e-wallet)'
            }),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }


class RefundForm(AdminInputMixin, forms.ModelForm):
    """Form for requesting a refund."""

    class Meta:
        model = Refund
        fields = ['refund_type', 'amount', 'reason', 'refund_method', 'notes']
        widgets = {
            'refund_type': forms.Select(),
            'amount': forms.NumberInput(attrs={
                'placeholder': '0.00',
                'step': '0.01',
                'min': '0.01'
            }),
            'reason': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Reason for refund'}),
            'refund_method': forms.Select(),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }


class VoidSaleForm(AdminInputMixin, forms.Form):
    """Form for voiding a sale."""

    reason = forms.CharField(
        max_length=200,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'placeholder': 'Reason for voiding this sale'
        })
    )


class QuickSearchForm(forms.Form):
    """Search form for finding products/services."""

    query = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Search products, medications, services...',
            'autocomplete': 'off'
        })
    )
    category = forms.ChoiceField(
        choices=[
            ('all', 'All Items'),
            ('service', 'Services'),
            ('product', 'Products'),
            ('medication', 'Medications'),
        ],
        required=False,
        initial='all'
    )
