"""Admin configuration for POS models."""

from django.contrib import admin

from .models import Sale, SaleItem, Payment, Refund, RefundItem


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    readonly_fields = ('line_total',)


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'branch', 'customer_display_name', 'total', 'status', 'created_at')
    list_filter = ('status', 'branch', 'customer_type', 'created_at')
    search_fields = ('transaction_id', 'guest_name', 'customer__email')
    readonly_fields = ('transaction_id', 'subtotal', 'total', 'amount_paid', 'change_due', 'created_at', 'completed_at')
    inlines = [SaleItemInline, PaymentInline]

    fieldsets = (
        ('Transaction Info', {
            'fields': ('transaction_id', 'branch', 'status')
        }),
        ('Customer', {
            'fields': ('customer_type', 'customer', 'pet', 'guest_name', 'guest_phone', 'guest_email')
        }),
        ('Financials', {
            'fields': ('subtotal', 'discount_amount', 'discount_reason', 'tax_amount', 'total')
        }),
        ('Payment', {
            'fields': ('amount_paid', 'change_due')
        }),
        ('Staff & Notes', {
            'fields': ('cashier', 'notes', 'voided_by', 'void_reason')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    list_display = ('sale', 'item_type', 'name', 'quantity', 'unit_price', 'line_total')
    list_filter = ('item_type',)
    search_fields = ('name', 'sale__transaction_id')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('sale', 'method', 'amount', 'status', 'created_at')
    list_filter = ('method', 'status')
    search_fields = ('sale__transaction_id', 'reference_number')


class RefundItemInline(admin.TabularInline):
    model = RefundItem
    extra = 0


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ('refund_id', 'sale', 'refund_type', 'amount', 'status', 'created_at')
    list_filter = ('status', 'refund_type')
    search_fields = ('refund_id', 'sale__transaction_id')
    readonly_fields = ('refund_id', 'created_at', 'completed_at')
    inlines = [RefundItemInline]
