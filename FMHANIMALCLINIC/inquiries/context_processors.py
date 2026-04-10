from .models import Inquiry


def new_inquiry_count(request):
    """
    Returns the count of new (unread) inquiries for the admin sidebar.
    Only shows for authenticated staff users with branch_admin or higher permissions.
    """
    if request.user.is_authenticated:
        # Check if user is staff with appropriate permissions
        if hasattr(request.user, 'assigned_role') and request.user.assigned_role:
            role_code = request.user.assigned_role.code
            # Only show inquiry count for admin roles
            if role_code in ['admin', 'branch_admin', 'super_admin']:
                try:
                    count = Inquiry.objects.filter(status='NEW').count()
                    return {'new_inquiry_count': count}
                except Exception:
                    # Table doesn't exist yet (migrations not run)
                    pass
    return {'new_inquiry_count': 0}
