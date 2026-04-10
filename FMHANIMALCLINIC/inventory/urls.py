"""
URL configuration for the inventory application.
"""
from django.urls import path
from . import views

app_name = 'inventory'  # pylint: disable=invalid-name

urlpatterns = [
    path('catalog/', views.catalog_view, name='catalog'),
    path('management/', views.inventory_management_view, name='management'),
    path('adjustment/new/', views.stock_adjustment_create_view,
         name='adjustment_new'),
    path('item/new/', views.product_create_view, name='product_new'),
    path('item/<int:pk>/edit/', views.product_edit_view, name='product_edit'),
    path('product/<int:pk>/reserve/', views.reserve_product_view,
         name='reserve_product'),
    path('reservation/<int:pk>/success/', views.reservation_success_view,
         name='reservation_success'),
    path('my-reservations/', views.my_reservations_view,
         name='my_reservations'),
    path('reservation/<int:pk>/confirm/', views.confirm_reservation_view,
         name='confirm_reservation'),
    path('reservation/<int:pk>/cancel/', views.cancel_reservation_view,
         name='cancel_reservation'),
    path('transfers/', views.stock_transfer_list_view, name='transfer_list'),
    path('transfers/request/', views.stock_transfer_request_view,
         name='transfer_request'),
    path('transfers/<int:pk>/update-status/',
         views.stock_transfer_update_status_view, name='transfer_update_status'),
    path('super-admin/overview/', views.super_admin_stock_view,
         name='super_admin_stock_monitoring'),
    path('super-admin/logs/', views.activity_logs_view,
         name='activity_logs'),
    path('super-admin/logs/<int:pk>/delete/', views.delete_activity_log,
         name='delete_activity_log'),
    path('super-admin/logs/clear/', views.clear_activity_logs,
         name='clear_activity_logs'),
    path('get-branch-products/<int:branch_id>/', views.get_branch_products,
         name='get_branch_products'),
]
