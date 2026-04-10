# pylint: disable=no-member, line-too-long, trailing-whitespace, missing-docstring, invalid-name, import-outside-toplevel
from django.urls import path
from . import views
from . import rbac_views

app_name = 'accounts'

urlpatterns = [
    # Authentication URLs (these also have legacy non-namespaced names via redirect)
    path('login/', views.login_view, name='login_page'),
    path('register/', views.register_view, name='register_page'),
    path('forgot-password/', views.forgot_password_view, name='forgot_password'),
    path('reset-password/', views.reset_password_view, name='reset_password'),
    path('change-password/', views.change_password_view, name='change_password'),
    path('verify-otp/', views.verify_otp_view, name='verify_otp'),
    path('select-branch/', views.select_branch_view, name='select_branch'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.user_dashboard_view, name='user_dashboard'),
    path('activity/<int:activity_id>/delete/', views.delete_activity_view, name='delete_activity'),
    path('activity/clear-all/', views.clear_all_activities_view, name='clear_all_activities'),
    path('admin-dashboard/', views.admin_dashboard_view, name='admin_dashboard'),
    path('vet-dashboard/', views.vet_dashboard_view, name='vet_dashboard'),
    path('receptionist-dashboard/', views.receptionist_dashboard_view, name='receptionist_dashboard'),
    path('profile/', views.profile_view, name='profile'),
    path('create-account/', views.admin_create_account, name='admin_create_account'),

    # Role Management URLs
    path('roles/', rbac_views.role_list, name='role_list'),
    path('roles/create/', rbac_views.role_create, name='role_create'),
    path('roles/<int:role_id>/', rbac_views.role_detail, name='role_detail'),
    path('roles/<int:role_id>/edit/', rbac_views.role_edit, name='role_edit'),
    path('roles/<int:role_id>/delete/', rbac_views.role_delete, name='role_delete'),

    # User Role Assignment URLs
    path('users/roles/', rbac_views.user_role_list, name='user_role_list'),
    path('users/<int:user_id>/assign-role/', rbac_views.assign_user_role, name='assign_user_role'),

    # API Endpoints
    path('api/roles/<int:role_id>/permissions/', rbac_views.get_role_permissions, name='role_permissions_api'),
    path('api/modules/', rbac_views.module_list_api, name='module_list_api'),
    
    # In-Profile Password Reset API
    path('api/profile/send-otp/', views.profile_send_otp_api, name='profile_send_otp_api'),
    path('api/profile/verify-otp/', views.profile_verify_otp_api, name='profile_verify_otp_api'),
    path('api/profile/reset-password/', views.profile_reset_password_api, name='profile_reset_password_api'),
]

# Legacy URL names for backward compatibility
# These are imported in the main urls.py to work without namespace
legacy_urlpatterns = [
    path('accounts/login/', views.login_view, name='login_page'),
    path('accounts/register/', views.register_view, name='register_page'),
    path('accounts/select-branch/', views.select_branch_view, name='select_branch'),
    path('accounts/logout/', views.logout_view, name='logout'),
    path('accounts/dashboard/', views.user_dashboard_view, name='user_dashboard'),
    path('accounts/admin-dashboard/', views.admin_dashboard_view, name='admin_dashboard'),
    path('accounts/vet-dashboard/', views.vet_dashboard_view, name='vet_dashboard'),
    path('accounts/receptionist-dashboard/', views.receptionist_dashboard_view, name='receptionist_dashboard'),
    path('accounts/profile/', views.profile_view, name='profile'),
]
