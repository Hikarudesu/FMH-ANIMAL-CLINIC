"""URL patterns for settings."""

from django.urls import path

from . import views

app_name = 'settings'

urlpatterns = [
    path('', views.settings_main, name='admin_settings'),
    # Direct tab URLs for bookmarking
    path('clinic/', views.settings_main, {'default_tab': 'clinic'}, name='clinic_settings'),
    path('scheduling/', views.settings_main, {'default_tab': 'scheduling'}, name='scheduling_settings'),
    path('inventory/', views.settings_main, {'default_tab': 'inventory'}, name='inventory_settings'),
    path('notifications/', views.settings_main, {'default_tab': 'notifications'}, name='notification_settings'),
    path('payroll/', views.settings_main, {'default_tab': 'payroll'}, name='payroll_settings'),
    path('system/', views.settings_main, {'default_tab': 'system'}, name='system_settings'),
    path('content/', views.settings_main, {'default_tab': 'content'}, name='content_settings'),
    
    # API endpoints for configurable options
    path('api/reason/<int:pk>/', views.reason_for_visit_detail, name='reason_detail'),
    path('api/status/<int:pk>/', views.clinical_status_detail, name='status_detail'),
    path('api/reorder-reason/', views.reorder_reasons, name='reorder_reasons'),
    path('api/reorder-status/', views.reorder_statuses, name='reorder_statuses'),
]
