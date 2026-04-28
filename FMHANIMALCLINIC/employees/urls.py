from django.urls import path
from . import views

app_name = 'employees'

urlpatterns = [
    # Staff Management
    path('staff/', views.staff_list, name='staff_list'),
    path('staff/<int:user_id>/edit/', views.staff_edit, name='staff_edit'),
    path('staff/<int:pk>/delete/', views.staff_delete, name='staff_delete'),

    # Schedule Calendar
    path('schedule/', views.schedule_view, name='schedule'),
    path('schedule/api/', views.schedule_api, name='schedule_api'),
    path('schedule/available-staff/', views.available_staff_api, name='available_staff_api'),
    path('schedule/add/', views.schedule_add, name='schedule_add'),
    path('schedule/<int:pk>/edit/', views.schedule_edit, name='schedule_edit'),
    path('schedule/clear-all/',
         views.schedule_clear_all, name='schedule_clear_all'),
    path('schedule/<int:pk>/delete/',
         views.schedule_delete, name='schedule_delete'),

    # Recurring Schedules
    path('schedule/recurring/', views.recurring_list, name='recurring_list'),
    path('schedule/recurring/add/', views.recurring_add, name='recurring_add'),
    path('schedule/recurring/<int:pk>/delete/',
         views.recurring_delete, name='recurring_delete'),
]
