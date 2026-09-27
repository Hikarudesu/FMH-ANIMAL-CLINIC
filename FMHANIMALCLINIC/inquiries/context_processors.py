from .models import Inquiry


def new_inquiry_count(request):
    """
    Returns the count of inquiries that have not been responded to for the
    current staff user's visible branch scope.
    """
    if request.user.is_authenticated:
        if getattr(request.user, 'is_clinic_staff', False):
            inquiries = Inquiry.objects.filter(status__in=('NEW', 'READ'))
            if (
                not request.user.is_superuser
                and request.user.is_module_branch_restricted('inquiries')
            ):
                if not request.user.branch:
                    inquiries = inquiries.none()
                else:
                    inquiries = inquiries.filter(branch=request.user.branch)
            count = inquiries.count()
            return {
                'new_inquiry_count': count,
                'unanswered_inquiry_count': count,
            }
    return {
        'new_inquiry_count': 0,
        'unanswered_inquiry_count': 0,
    }
