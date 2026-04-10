"""
URL configurations for the patients app.
"""
from django.urls import path
from . import views

# pylint: disable=invalid-name
app_name = 'patients'

urlpatterns = [
    path('admin/list/', views.admin_list_view, name='admin_list'),
    path('admin/add/', views.admin_add_pet_view, name='admin_add_pet'),
    path('admin/<int:pk>/', views.admin_detail_view, name='admin_detail'),
    path('admin/<int:pk>/edit/', views.admin_edit_pet_view, name='admin_edit_pet'),
    path('admin/<int:pk>/delete/', views.admin_delete_pet_view, name='admin_delete_pet'),
    path('admin/owner/<int:user_id>/', views.admin_owner_detail_view, name='admin_owner_detail'),
    path('admin/owner/<int:user_id>/notification/<int:notification_id>/delete/', views.delete_notification_view, name='delete_notification'),
    path('admin/owner/<int:user_id>/notifications/clear/', views.clear_all_notifications_view, name='clear_all_notifications'),
    path('admin/owner/<int:user_id>/activity/<int:activity_id>/delete/', views.delete_activity_view, name='delete_activity'),
    path('admin/owner/<int:user_id>/activities/clear/', views.clear_all_activities_view, name='clear_all_activities'),
    path('my-pets/', views.my_pets_view, name='my_pets'),
    path('add/', views.add_pet_view, name='add_pet'),
    path('<int:pk>/', views.user_pet_detail_view, name='user_pet_detail'),
    path('<int:pk>/edit/', views.edit_pet_view, name='edit_pet'),
    path('<int:pk>/delete/', views.delete_pet_view, name='delete_pet'),
]
