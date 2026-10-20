from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date
from dateutil.relativedelta import relativedelta

from accounts.decorators import module_permission_required
from branches.models import Branch
from disease_geo_mapping.services import CONTROLLED_DISEASE_TYPES, summarize_branch_disease_trends
from records.models import RecordEntry


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


def _branch_has_records(branch):
    if not branch:
        return False
    return RecordEntry.objects.filter(
        Q(record__branch=branch) | Q(record__pet__branch=branch)
    ).exists()


def _get_branch_selection(request, branches, branch_restricted):
    if branch_restricted:
        if request.user.branch_id:
            preferred_branch = branches.filter(pk=request.user.branch_id).first()
            if preferred_branch and preferred_branch.is_active:
                return preferred_branch
        return None

    branch_id = request.GET.get('branch')
    if branch_id:
        selected_branch = branches.filter(pk=branch_id).first()
        if selected_branch:
            return selected_branch

    for branch in branches:
        if _branch_has_records(branch):
            return branch

    return branches.first() if branches.exists() else None


@login_required
@module_permission_required('disease_geo_mapping', 'VIEW')
def dashboard(request):
    """Render the Disease Geo Mapping dashboard with RBAC-aware branch filtering."""
    branch_restricted = request.user.is_module_branch_restricted('disease_geo_mapping')
    branches = Branch.objects.filter(is_active=True).order_by('name')

    if branch_restricted:
        branches = branches.filter(pk=request.user.branch_id) if request.user.branch_id else Branch.objects.none()

    selected_branch = _get_branch_selection(request, branches, branch_restricted)

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
        'branch_restricted': branch_restricted,
        'selected_disease_type': disease_type,
        'available_diseases': payload.get('available_diseases', []),
        'date_from': start_date.isoformat(),
        'date_to': end_date.isoformat(),
        'date_min': earliest_date.isoformat(),
        'date_max': today.isoformat(),
        'show_assumption_banner': True,
    })

    return render(request, 'disease_geo_mapping/dashboard.html', payload)
