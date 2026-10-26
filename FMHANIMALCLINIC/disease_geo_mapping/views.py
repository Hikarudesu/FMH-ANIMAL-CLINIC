from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date
from dateutil.relativedelta import relativedelta

from accounts.decorators import special_permission_required
from accounts.rbac_models import SpecialPermissionCodes
from branches.models import Branch
from disease_geo_mapping.services import CONTROLLED_DISEASE_TYPES, summarize_branch_disease_trends


def _parse_iso_date(value):
    if not value:
        return None
    parsed = parse_date(value)
    return parsed


def _get_analysis_date_range(date_from, date_to, today):
    """Keep analysis dates within the previous six calendar months."""
    earliest_date = today - relativedelta(months=6)
    start_date = _parse_iso_date(date_from) or earliest_date
    end_date = _parse_iso_date(date_to) or today

    start_date = min(max(start_date, earliest_date), today)
    end_date = min(max(end_date, earliest_date), today)
    if start_date > end_date:
        start_date = end_date

    return earliest_date, start_date, end_date


def _get_user_branch(user):
    branch = getattr(user, 'branch', None)
    if branch:
        return branch
    try:
        return user.staff_profile.branch
    except ObjectDoesNotExist:
        return None


@login_required
@special_permission_required(SpecialPermissionCodes.DISEASE_GEO_MAPPING)
def dashboard(request):
    """Render disease trends for the authenticated user's assigned branch only."""
    user_branch = _get_user_branch(request.user)
    branches = Branch.objects.filter(
        pk=user_branch.pk, is_active=True,
    ).order_by('name') if user_branch else Branch.objects.none()
    selected_branch = branches.first()

    today = timezone.localdate()
    earliest_date, start_date, end_date = _get_analysis_date_range(
        request.GET.get('date_from'),
        request.GET.get('date_to'),
        today,
    )
    disease_type = request.GET.get('disease_type') or ''

    payload = summarize_branch_disease_trends(
        selected_branch,
        start_date=start_date,
        end_date=end_date,
        disease_type=disease_type,
    )

    payload.update({
        'branches': branches,
        'selected_branch_id': str(selected_branch.id) if selected_branch else '',
        'branch_restricted': True,
        'selected_disease_type': disease_type,
        'available_diseases': payload.get('available_diseases', []),
        'date_from': start_date.isoformat(),
        'date_to': end_date.isoformat(),
        'date_min': earliest_date.isoformat(),
        'date_max': today.isoformat(),
        'show_assumption_banner': True,
    })

    return render(request, 'disease_geo_mapping/dashboard.html', payload)
