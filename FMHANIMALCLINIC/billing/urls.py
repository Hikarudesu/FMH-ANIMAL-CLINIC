"""URL configuration for the billing app — services management."""
from django.urls import path
from . import views

app_name = 'billing'

urlpatterns = [
    # Services Management (Products/Medications)
    path('services/', views.service_list,
         name='billable_items'),
    path('services/create/', views.ServiceCreateView.as_view(),
         name='billable_item_create'),
    path('services/<int:pk>/update/',
         views.ServiceUpdateView.as_view(), name='billable_item_update'),
    path('services/<int:pk>/delete/',
         views.service_delete, name='billable_item_delete'),
    path('my-statements/', views.my_statements, name='my_statements'),
    path('my-statements/<int:pk>/', views.my_statement_detail, name='my_statement_detail'),

]
