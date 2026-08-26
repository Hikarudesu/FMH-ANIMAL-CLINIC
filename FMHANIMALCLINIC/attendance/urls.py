"""URL patterns for Attendance and Biometrics module."""
from django.urls import path
from . import views

app_name = 'attendance'

urlpatterns = [
    # Dashboard
    path('', views.attendance_dashboard, name='dashboard'),
    
    # Device Management
    path('devices/', views.device_list, name='device_list'),
    path('devices/create/', views.device_create, name='device_create'),
    path('devices/<int:device_id>/edit/', views.device_edit, name='device_edit'),
    path('devices/<int:device_id>/', views.device_detail, name='device_detail'),
    
    # Import
    path('import/', views.attendance_import, name='import'),
    
    # Monthly Review & Approval
    path('review/', views.attendance_review, name='review'),
    path('attendance/<int:attendance_id>/edit/', views.attendance_edit, name='attendance_edit'),
    path('attendance/<int:attendance_id>/approve/', views.attendance_approve, name='attendance_approve'),
    
    # Reports
    path('summary/', views.attendance_summary, name='summary'),
]
