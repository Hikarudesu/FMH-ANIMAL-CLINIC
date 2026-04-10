from django.urls import path
from . import views

app_name = 'appointments'

urlpatterns = [
    # Public booking (no login required)
    path('book/', views.public_book, name='public_book'),
    path('book/success/', views.book_success, name='book_success'),

    # Portal booking (login required)
    path('portal/book/', views.portal_book, name='portal_book'),
    path('my/', views.my_appointments, name='my_appointments'),

    # AJAX API endpoints
    path('api/vets/', views.api_available_vets, name='api_vets'),
    path('api/times/', views.api_vet_times, name='api_times'),
    path('api/dates/', views.api_available_dates, name='api_dates'),
    path('api/owners/', views.api_pet_owners, name='api_owners'),
    path('api/pets/', views.api_owner_pets, name='api_pets'),

    # Admin management
    path('admin/', views.admin_list, name='admin_list'),
    path('admin/calendar-api/', views.admin_calendar_api,
         name='admin_calendar_api'),
    path('admin/quick-create/', views.admin_quick_create,
         name='admin_quick_create'),
    path('admin/<int:pk>/edit/', views.admin_edit, name='admin_edit'),
    path('admin/<int:pk>/delete/', views.admin_delete, name='admin_delete'),
]
