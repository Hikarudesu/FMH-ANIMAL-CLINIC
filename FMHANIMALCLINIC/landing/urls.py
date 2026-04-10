from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_view, name='landing_page'),
    path('about/', views.about_view, name='aboutus_page'),
    path('services/', views.services_view, name='services_page'),
    path('contact/', views.contact_view, name='contact_page'),
]
