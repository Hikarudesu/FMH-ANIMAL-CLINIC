from django.urls import path
from . import views

app_name = 'branches'

urlpatterns = [
    path('', views.branch_list, name='list'),
    path('add/', views.branch_create, name='add'),
    path('<int:pk>/edit/', views.branch_update, name='edit'),
    path('<int:pk>/delete/', views.branch_delete, name='delete'),
]
