"""Context processors for the accounts app."""
from typing import Dict

from django.http import HttpRequest


def navigation_modules(request: HttpRequest) -> Dict[str, object]:
    """Expose navigation modules ordered by display_order.

    Returns a dict with key `nav_modules` containing a QuerySet or list
    of Module objects that should be displayed in the sidebar for the
    current request's user.
    """
    try:
        from accounts.rbac_models import Module
    except Exception:
        return {"nav_modules": []}

    # If request has an authenticated user, use the user's accessible modules
    user = getattr(request, 'user', None)
    if user and hasattr(user, 'get_accessible_modules'):
        try:
            modules = user.get_accessible_modules().order_by('display_order')
        except Exception:
            # In case get_accessible_modules returns list instead of QS
            modules = sorted(list(user.get_accessible_modules()), key=lambda m: getattr(m, 'display_order', 0))
        return {"nav_modules": modules}

    # Fallback: return active modules ordered by display_order
    try:
        return {"nav_modules": Module.objects.filter(is_active=True).order_by('display_order')}
    except Exception:
        return {"nav_modules": []}
