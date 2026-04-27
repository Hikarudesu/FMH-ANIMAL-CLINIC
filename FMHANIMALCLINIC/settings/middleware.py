"""Middleware for system settings."""

from datetime import datetime

from django.conf import settings
from django.shortcuts import redirect
from django.contrib import messages
from django.utils import timezone


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