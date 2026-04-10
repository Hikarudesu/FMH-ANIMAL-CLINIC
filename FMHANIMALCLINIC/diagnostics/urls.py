from django.urls import path
from . import views

app_name = 'diagnostics'

urlpatterns = [
    # Dashboard
    path('admin/', views.dashboard, name='dashboard'),

    # Run diagnosis
    path('admin/run/<int:pet_id>/', views.run_diagnosis, name='run_diagnosis'),

    # Diagnosis detail
    path('admin/<int:pk>/', views.diagnosis_detail, name='detail'),

    # Mark as reviewed
    path('admin/<int:pk>/review/', views.mark_reviewed, name='mark_reviewed'),

    # Delete diagnosis
    path('admin/<int:pk>/delete/', views.delete_diagnosis, name='delete'),

    # API: Pet diagnosis history
    path('api/pet/<int:pet_id>/history/', views.pet_diagnosis_history, name='pet_history'),
]
