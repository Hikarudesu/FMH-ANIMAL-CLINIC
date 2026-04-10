"""
Admin configuration for the inventory application.
"""
from django.contrib import admin
from .models import Product, StockAdjustment, Reservation, StockTransfer


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """Admin configuration for Product model."""
    list_display = ('name', 'branch', 'item_type', 'price',
                    'stock_quantity', 'is_available', 'updated_at')
    list_filter = ('branch', 'item_type', 'is_available')
    search_fields = ('name', 'sku', 'barcode', 'description')
    list_editable = ('price', 'stock_quantity', 'is_available')
    readonly_fields = ('sku', 'created_at', 'updated_at')
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'item_type', 'branch')
        }),
        ('Inventory & Identification', {
            'fields': (
                'sku', 'barcode', 'manufacturer', 'stock_quantity',
                'min_stock_level', 'is_available'
            )
        }),
        ('Pricing & Financials', {
            'fields': ('unit_cost', 'price')
        }),
        ('Safety & Dates', {
            'fields': ('expiration_date', 'created_at', 'updated_at')
        }),
    )


@admin.register(StockAdjustment)
class StockAdjustmentAdmin(admin.ModelAdmin):
    """Admin configuration for StockAdjustment model."""
    list_display = ('product', 'adjustment_type', 'quantity',
                    'date', 'branch', 'reference')
    list_filter = ('adjustment_type', 'branch', 'date')
    search_fields = ('product__name', 'reference', 'reason')
    date_hierarchy = 'date'


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    """Admin configuration for Reservation model."""
    list_display = ('id', 'user', 'product', 'quantity',
                    'status', 'created_at')
    list_filter = ('status', 'created_at', 'product__branch')
    search_fields = ('user__username', 'user__email', 'product__name', 'notes')
    list_editable = ('status',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(StockTransfer)
class StockTransferAdmin(admin.ModelAdmin):
    """Admin configuration for StockTransfer model."""
    list_display = ('id', 'source_product', 'destination_branch',
                    'quantity', 'status', 'created_at')
    list_filter = ('status', 'destination_branch', 'created_at')
    search_fields = ('source_product__name', 'notes')
    readonly_fields = ('created_at', 'updated_at')
