"""
Simplified URL patterns for FMH Animal Clinic Payroll.

Tab Navigation:
1. Dashboard (overview with stats)
2. Vets (employee list with payroll history)
3. Requests (payroll period management)
4. Audit Log (transaction & system action history)
"""
from django.urls import path
from . import views

app_name = 'payroll'

urlpatterns = [
    # Main Tabs
    path('', views.payroll_dashboard, name='dashboard'),
    path('vets/', views.payroll_vets, name='vets'),
    path('requests/', views.payroll_requests, name='requests'),
    
    # Generate Payslips
    path('generate/', views.generate_payslips, name='generate'),
    path('generate/action/', views.generate_payslips_action, name='generate_action'),
    
    # Payslips List & Edit
    path('period/<int:period_id>/', views.payslips_list, name='payslips'),
    path('payslip/<int:payslip_id>/edit/', views.payslip_edit, name='payslip_edit'),
    path('payslip/<int:payslip_id>/delete/', views.payslip_delete, name='payslip_delete'),
    path('payslip/<int:payslip_id>/print/', views.payslip_print, name='payslip_print'),
    path('payslip/<int:payslip_id>/approve/', views.payslip_approve, name='payslip_approve'),
    
    # Period Actions
    path('period/<int:period_id>/release/', views.release_payroll, name='release'),
    path('period/<int:period_id>/approve-all/', views.approve_all_payslips, name='approve_all'),
    path('period/<int:period_id>/delete/', views.delete_period, name='delete_period'),
    
    # Vet Management
    path('vet/<int:staff_id>/', views.vet_detail, name='vet_detail'),
    
    # Audit Log
    path('audit/', views.audit_log_view, name='audit_log'),
    path('audit/<int:log_id>/', views.audit_log_detail, name='audit_log_detail'),
    
    # Export Features
    path('period/<int:period_id>/export/csv/', views.export_payslips_csv, name='export_csv'),
    path('period/<int:period_id>/export/excel/', views.export_payslips_excel, name='export_excel'),
    
    # Email Features
    path('payslip/<int:payslip_id>/email/', views.send_payslip_email, name='send_email'),
    path('period/<int:period_id>/email-all/', views.send_payslips_bulk, name='send_bulk_email'),

    # Staff Self-Service
    path('my-payslips/', views.my_payslips_view, name='my_payslips'),
    path('my-payslips/<int:pk>/', views.my_payslip_detail_view, name='my_payslip_detail'),
]
