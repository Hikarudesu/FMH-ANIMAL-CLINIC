"""Middleware for system settings."""

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

        # Hardcoded session timeout: 30 minutes
        timeout_minutes = 30
        timeout_seconds = timeout_minutes * 60

        # Check last activity
        last_activity = request.session.get('last_activity')
        if last_activity:
            last_activity_time = timezone.datetime.fromisoformat(last_activity)
            if (timezone.now() - last_activity_time).total_seconds() > timeout_seconds:
                # Session expired - logout user
                from django.contrib.auth import logout
                logout(request)
                messages.warning(request, f'Your session has expired due to inactivity. Please log in again.')
                return redirect('login')

        # Update last activity
        request.session['last_activity'] = timezone.now().isoformat()
        request.session.modified = True

        return self.get_response(request)