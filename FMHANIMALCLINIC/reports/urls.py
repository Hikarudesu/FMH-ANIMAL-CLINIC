"""URL configuration for Reports & Analytics module."""

from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    # Main Analytics Dashboard
    path('analytics/', views.analytics_dashboard, name='analytics_dashboard'),

    # Excel Exports
    path('export/analytics/', views.export_analytics_excel, name='export_analytics_excel'),
]
