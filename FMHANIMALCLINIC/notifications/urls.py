from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    path('', views.user_notifications, name='notification_list'),
    path('admin/', views.admin_notification_list, name='admin_notifications'),
    path('<int:pk>/read/', views.mark_read, name='mark_read'),
    path('<int:pk>/delete/', views.delete_notification, name='delete_notification'),
    path('mark-all-read/', views.mark_all_read, name='mark_all_read'),
    path('delete-all/', views.delete_all_notifications, name='delete_all'),
]
