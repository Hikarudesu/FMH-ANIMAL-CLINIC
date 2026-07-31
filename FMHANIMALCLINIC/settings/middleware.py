"""Middleware for system settings."""

from datetime import datetime

from django.conf import settings
from django.shortcuts import redirect
from django.contrib import messages
from django.utils import timezone

from .utils import get_setting


class SessionTimeoutMiddleware:
    """
    Middleware to enforce session timeout with hardcoded values.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip for anonymous users
        if not request.user.is_authenticated:
            return self.get_response(request)

        # Skip for API endpoints and static files
        if (request.path.startswith('/api/') or
            request.path.startswith('/static/') or
            request.path.startswith('/media/') or
            request.path.startswith('/admin/')):
            return self.get_response(request)

        # Session timeout defaults to 24 hours of inactivity.
        timeout_seconds = int(getattr(settings, 'SESSION_COOKIE_AGE', 24 * 60 * 60))

        # Check last activity
        last_activity = request.session.get('last_activity')
        if last_activity:
            try:
                last_activity_time = datetime.fromisoformat(last_activity)
                if timezone.is_naive(last_activity_time):
                    last_activity_time = timezone.make_aware(
                        last_activity_time,
                        timezone.get_current_timezone(),
                    )
            except (TypeError, ValueError):
                last_activity_time = None

            if last_activity_time and (timezone.now() - last_activity_time).total_seconds() > timeout_seconds:
                # Session expired - logout user and redirect to a valid login route.
                from django.contrib.auth import logout
                logout(request)
                messages.warning(
                    request,
                    'Your session expired after 24 hours of inactivity. Please log in again.',
                )
                return redirect('accounts:login_page')

        # Update last activity
        request.session['last_activity'] = timezone.now().isoformat()
        request.session.set_expiry(timeout_seconds)
        request.session.modified = True

        return self.get_response(request)


class MaintenanceModeMiddleware:
    """Restrict access during maintenance mode to staff and superadmin."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        maintenance_mode = get_setting('system_maintenance_mode', False)
        if not maintenance_mode:
            return self.get_response(request)

        allowed_paths = [
            settings.STATIC_URL,
            settings.MEDIA_URL,
            '/admin/',
            '/accounts/login/',
            '/accounts/forgot-password/',
            '/accounts/reset-password/',
            '/accounts/verify-otp/',
            '/accounts/logout/',
            '/accounts/register/',
        ]

        if any(request.path.startswith(path) for path in allowed_paths):
            return self.get_response(request)

        maintenance_message = get_setting(
            'system_maintenance_message',
            'The system is currently under maintenance. Only staff and superadmin may log in at this time.'
        )

        if request.user.is_authenticated and not request.user.is_clinic_staff():
            from django.contrib.auth import logout
            logout(request)
            messages.warning(request, maintenance_message)
            return redirect('accounts:login_page')

        return self.get_response(request)