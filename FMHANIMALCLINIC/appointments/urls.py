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
    path(
        'my/<int:pk>/',
        views.portal_appointment_detail,
        name='portal_detail',
    ),
    path('my/history/', views.my_appointment_history, name='my_appointment_history'),
    path(
        'my/history/search/',
        views.my_appointment_history_search,
        name='my_appointment_history_search',
    ),
    path(
        'my/history/<int:pk>/',
        views.my_appointment_history_detail,
        name='my_appointment_history_detail',
    ),
    path('my/<int:pk>/cancel/', views.portal_cancel, name='portal_cancel'),

    # AJAX API endpoints
    path('api/vets/', views.api_available_vets, name='api_vets'),
    path('api/times/', views.api_vet_times, name='api_times'),
    path('api/dates/', views.api_available_dates, name='api_dates'),
    path('api/owners/', views.api_pet_owners, name='api_owners'),
    path(
        'api/check-owner-identity/',
        views.api_check_owner_identity,
        name='api_check_owner_identity',
    ),
    path(
        'api/check-portal-owner-email/',
        views.api_check_portal_owner_email,
        name='api_check_portal_owner_email',
    ),
    path(
        'api/check-booking-owner-email/',
        views.api_check_booking_owner_email,
        name='api_check_booking_owner_email',
    ),
    path(
        'api/public-check-owner-identity/',
        views.api_check_public_owner_identity,
        name='api_check_public_owner_identity',
    ),
    path('api/pets/', views.api_owner_pets, name='api_pets'),
    path('api/walkin-guests/', views.api_walkin_guests, name='api_walkin_guests'),
    path('api/walkin-guest-pets/', views.api_walkin_guest_pets, name='api_walkin_guest_pets'),

    # Admin management
    path('admin/', views.admin_list, name='admin_list'),
    path(
        'admin/search/',
        views.api_search_admin_appointments,
        name='api_search_admin',
    ),
    path(
        'admin/history/',
        views.admin_appointment_history,
        name='admin_appointment_history',
    ),
    path(
        'admin/history/<int:pk>/',
        views.admin_appointment_history_detail,
        name='admin_appointment_history_detail',
    ),
    path('admin/calendar-api/', views.admin_calendar_api,
         name='admin_calendar_api'),
    path('admin/quick-create/', views.admin_quick_create,
         name='admin_quick_create'),
    path('admin/<int:pk>/delete/', views.admin_delete, name='admin_delete'),
    path('admin/<int:pk>/', views.admin_detail, name='admin_detail'),
    path('admin/<int:pk>/workflow/<slug:action>/', views.admin_workflow_action,
         name='admin_workflow_action'),
    path('vet/<int:pk>/workflow/<slug:action>/', views.veterinarian_workflow_action,
         name='vet_workflow_action'),
    path('admin/<int:pk>/edit/', views.admin_edit, name='admin_edit'),
]
