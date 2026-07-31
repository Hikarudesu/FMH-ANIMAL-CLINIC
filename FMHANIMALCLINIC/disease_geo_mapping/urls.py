from django.urls import path

from . import views

app_name = 'disease_geo_mapping'

urlpatterns = [
    path('admin/', views.dashboard, name='dashboard'),
]
