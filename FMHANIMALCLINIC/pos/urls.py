"""URL configuration for POS module."""

from django.urls import path
from . import views

app_name = 'pos'

urlpatterns = [
    # Main POS checkout
    path('', views.checkout, name='checkout'),
    path('checkout/', views.checkout, name='checkout_alt'),

    # AJAX endpoints for checkout
    path('api/add-item/', views.add_item, name='add_item'),
    path('api/remove-item/', views.remove_item, name='remove_item'),
    path('api/update-quantity/', views.update_item_quantity, name='update_quantity'),
    path('api/update-sale/', views.update_sale_info, name='update_sale'),
    path('api/process-payment/', views.process_payment, name='process_payment'),
    path('api/filter-items/', views.filter_items_by_branch, name='filter_items'),

    # Search endpoints
    path('api/search/items/', views.search_items, name='search_items'),
    path('api/search/customers/', views.search_customers, name='search_customers'),

    # Sales management
    path('sales/', views.sales_list, name='sales_list'),
    path('sales/<int:sale_id>/', views.sale_detail, name='sale_detail'),
    path('sales/<int:sale_id>/receipt/', views.receipt, name='receipt'),
    path('sales/<int:sale_id>/void/', views.void_sale, name='void_sale'),
    path('sales/<int:sale_id>/cancel/', views.cancel_sale, name='cancel_sale'),

    # Statement of Account from Sale
    path('sales/<int:sale_id>/soa/', views.sale_soa, name='sale_soa'),
    path('sales/<int:sale_id>/soa/edit/', views.edit_soa, name='edit_soa'),
    path('sales/<int:sale_id>/send-soa/', views.send_soa, name='send_soa'),

    # Refunds
    path('sales/<int:sale_id>/refund/', views.refund_request, name='refund_request'),
    path('refunds/', views.refund_list, name='refund_list'),
    path('refunds/<int:refund_id>/approve/', views.refund_approve, name='refund_approve'),
    path('refunds/<int:refund_id>/complete/', views.refund_complete, name='refund_complete'),
    path('refunds/<int:refund_id>/reject/', views.refund_reject, name='refund_reject'),
]
