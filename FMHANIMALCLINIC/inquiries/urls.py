from django.urls import path
from . import views

app_name = 'inquiries'

urlpatterns = [
    # Public endpoint for contact form submission
    path('submit/', views.submit_inquiry, name='submit'),
    
    # Admin views
    path('', views.inquiry_list, name='list'),
    path('<int:pk>/', views.inquiry_detail, name='detail'),
    path('<int:pk>/update-status/', views.inquiry_update_status, name='update_status'),
    path('bulk-action/', views.inquiry_bulk_action, name='bulk_action'),
    
    # API
    path('api/stats/', views.get_inquiry_stats, name='api_stats'),
    
]
