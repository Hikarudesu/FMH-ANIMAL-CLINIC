"""
URL patterns for the records application block.
"""
from django.urls import path
from . import views

app_name = 'records'  # pylint: disable=invalid-name

urlpatterns = [
    path('admin/', views.admin_records_list, name='admin_list'),
    path('admin/create/', views.admin_record_create, name='admin_create'),
    path('admin/<int:pk>/', views.admin_record_detail, name='admin_detail'),
    path('admin/<int:pk>/edit/', views.admin_record_edit, name='admin_edit'),
    path('admin/<int:pk>/delete/', views.admin_record_delete, name='admin_delete'),
    path('admin/<int:pk>/add-entry/', views.admin_add_entry, name='admin_add_entry'),
    path('admin/entry/<int:entry_pk>/edit/', views.admin_entry_edit, name='admin_entry_edit'),
    path('admin/entry/<int:entry_pk>/delete/', views.admin_entry_delete, name='admin_entry_delete'),
    path('api/search-owners/', views.api_search_owners, name='api_search_owners'),
    path('<int:pk>/download-pdf/', views.download_pdf_view, name='download_pdf'),
    path('<int:pk>/view/', views.user_record_detail, name='user_detail'),
]
