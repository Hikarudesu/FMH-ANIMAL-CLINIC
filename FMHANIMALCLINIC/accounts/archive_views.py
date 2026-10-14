"""Super-admin views for retained records of deactivated pet-owner accounts."""

from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Prefetch, Q
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import admin_only
from accounts.models import OwnerAccountLink, User
from appointments.models import Appointment
from billing.models import CustomerStatement, Service
from branches.models import Branch
from diagnostics.models import AIDiagnosis
from inventory.models import Product, Reservation
from patients.models import Pet
from pos.models import Sale
from records.models import MedicalFile, MedicalRecord, RecordEntry

ARCHIVE_RETENTION_DAYS = 30
ARCHIVE_TYPE_FILTERS = (
    ('', 'All record types'),
    ('pet', 'Pets / patients'),
    ('medical_record', 'Medical records'),
    ('record_entry', 'Visit history'),
    ('medical_file', 'Medical files'),
    ('product', 'Inventory items'),
    ('service', 'Clinic services'),
)
ARCHIVE_RETENTION_FILTERS = (
    ('', 'All retention states'),
    ('restorable', 'Restorable'),
    ('expired', 'Past 30 days'),
)


@login_required
@admin_only
def owner_archive(request):
    search_query = request.GET.get('q', request.POST.get('q', '')).strip()
    branch_id = request.GET.get('branch', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    owners = User.objects.filter(
        owner_account_deactivated_at__isnull=False,
    ).select_related(
        'branch', 'owner_account_link__new_owner', 'owner_account_link__linked_by',
    ).order_by('-owner_account_deactivated_at', 'last_name', 'first_name')

    if search_query:
        owners = owners.filter(
            Q(first_name__icontains=search_query)
            | Q(last_name__icontains=search_query)
            | Q(username__icontains=search_query)
            | Q(email__icontains=search_query)
            | Q(pets__name__icontains=search_query)
        ).distinct()

    if branch_id.isdigit():
        owners = owners.filter(
            Q(branch_id=branch_id) | Q(pets__branch_id=branch_id)
        ).distinct()

    date_from_value = parse_date(date_from)
    date_to_value = parse_date(date_to)
    if date_from_value:
        owners = owners.filter(owner_account_deactivated_at__date__gte=date_from_value)
    if date_to_value:
        owners = owners.filter(owner_account_deactivated_at__date__lte=date_to_value)

    page_obj = Paginator(owners, 15).get_page(request.GET.get('page'))
    archived_owners = []
    for owner in page_obj.object_list:
        pets = Pet.all_objects.filter(owner=owner).select_related(
            'branch', 'clinical_status'
        ).order_by('name')
        if branch_id.isdigit():
            pets = pets.filter(branch_id=branch_id)
        pets = list(pets)
        pet_ids = [pet.pk for pet in pets]

        medical_records = MedicalRecord.all_objects.filter(
            pet_id__in=pet_ids,
        ).select_related('pet', 'branch', 'vet').prefetch_related(
            Prefetch('entries', queryset=RecordEntry.all_objects.all()),
            Prefetch('medical_files', queryset=MedicalFile.all_objects.all()),
        ).order_by('-date_recorded')
        if branch_id.isdigit():
            medical_records = medical_records.filter(branch_id=branch_id)
        records_by_pet = {pet.pk: [] for pet in pets}
        for record in medical_records:
            records_by_pet[record.pet_id].append(record)

        diagnoses = AIDiagnosis.objects.filter(pet_id__in=pet_ids).select_related(
            'pet'
        ).order_by('-created_at')
        diagnoses_by_pet = {pet.pk: [] for pet in pets}
        for diagnosis in diagnoses:
            diagnoses_by_pet[diagnosis.pet_id].append(diagnosis)

        appointments = Appointment.objects.filter(
            Q(user=owner) | Q(pet__owner=owner)
        ).select_related('branch', 'pet', 'preferred_vet').distinct().order_by('-appointment_date', '-appointment_time')
        sales = Sale.objects.filter(
            Q(customer=owner) | Q(pet__owner=owner)
        ).select_related('branch', 'pet').distinct().order_by('-created_at')
        statements = CustomerStatement.objects.filter(
            Q(customer=owner) | Q(sale__customer=owner) | Q(sale__pet__owner=owner)
        ).select_related('branch', 'sale').distinct().order_by('-date', '-created_at')
        reservations = Reservation.objects.filter(user=owner).select_related(
            'product', 'product__branch'
        ).order_by('-created_at')

        if branch_id.isdigit():
            appointments = appointments.filter(branch_id=branch_id)
            sales = sales.filter(branch_id=branch_id)
            statements = statements.filter(Q(branch_id=branch_id) | Q(sale__branch_id=branch_id))
            reservations = reservations.filter(product__branch_id=branch_id)

        pet_sections = [
            {
                'pet': pet,
                'medical_records': records_by_pet[pet.pk],
                'diagnoses': diagnoses_by_pet[pet.pk],
            }
            for pet in pets
        ]
        archived_owners.append({
            'owner': owner,
            'link_record': getattr(owner, 'owner_account_link', None),
            'pets': pet_sections,
            'appointments': appointments,
            'sales': sales,
            'statements': statements,
            'reservations': reservations,
            'counts': {
                'pets': len(pets),
                'appointments': appointments.count(),
                'sales': sales.count(),
                'statements': statements.count(),
                'reservations': reservations.count(),
                'medical_records': sum(len(section['medical_records']) for section in pet_sections),
            },
        })

    return render(request, 'accounts/owner_archive.html', {
        'page_obj': page_obj,
        'archived_owners': archived_owners,
        'branches': Branch.objects.filter(is_active=True).order_by('name'),
        'search_query': search_query,
        'selected_branch': branch_id,
        'date_from': date_from,
        'date_to': date_to,
        'archive_count': page_obj.paginator.count,
    })


@login_required
@admin_only
def link_archived_owner(request, owner_id):
    """Transfer retained records to a replacement pet-owner account."""
    archived_owner = get_object_or_404(
        User.objects.select_related('branch'),
        pk=owner_id,
        owner_account_deactivated_at__isnull=False,
    )
    existing_link = OwnerAccountLink.objects.filter(
        archived_owner=archived_owner,
    ).select_related('new_owner').first()
    if existing_link:
        messages.info(
            request,
            f'These records are already linked to {existing_link.new_owner.get_full_name() or existing_link.new_owner.username}.',
        )
        return redirect('accounts:owner_archive')

    eligible_owners = User.objects.filter(
        is_active=True,
        is_superuser=False,
        owner_account_deactivated_at__isnull=True,
    ).filter(
        Q(assigned_role__isnull=True) | Q(assigned_role__is_staff_role=False),
    ).filter(
        staff_profile__isnull=True,
    ).exclude(pk=archived_owner.pk)

    search_query = request.GET.get('q', '').strip()
    candidates = eligible_owners.none()
    if len(search_query) >= 2:
        for term in search_query.split():
            eligible_owners = eligible_owners.filter(
                Q(first_name__icontains=term)
                | Q(last_name__icontains=term)
                | Q(username__icontains=term)
                | Q(email__icontains=term)
            )
        candidates = eligible_owners.select_related('branch').order_by(
            'first_name', 'last_name', 'username',
        )[:50]

    if request.method == 'POST':
        if request.POST.get('confirm_link') != 'on':
            messages.error(request, 'Confirm the account link before transferring records.')
        else:
            new_owner = eligible_owners.filter(
                pk=request.POST.get('new_owner_id'),
            ).select_related('branch').first()
            if new_owner is None:
                messages.error(request, 'Select an active pet-owner account to receive these records.')
            else:
                with transaction.atomic():
                    archived_owner = User.objects.select_for_update().get(pk=archived_owner.pk)
                    if OwnerAccountLink.objects.filter(archived_owner=archived_owner).exists():
                        messages.error(request, 'These records have already been linked to another account.')
                        return redirect('accounts:owner_archive')

                    target_branch = Branch.objects.filter(
                        pk=new_owner.branch_id,
                        is_active=True,
                    ).first()
                    pets = Pet.all_objects.filter(owner=archived_owner)
                    pet_ids = list(pets.values_list('pk', flat=True))
                    appointments = Appointment.objects.filter(
                        Q(user=archived_owner) | Q(pet__owner=archived_owner),
                    ).distinct()
                    sales = Sale.objects.filter(
                        Q(customer=archived_owner) | Q(pet__owner=archived_owner),
                    ).distinct()
                    statements = CustomerStatement.objects.filter(
                        Q(customer=archived_owner)
                        | Q(sale__customer=archived_owner)
                        | Q(sale__pet__owner=archived_owner),
                    ).distinct()
                    reservations = Reservation.objects.filter(user=archived_owner)
                    record_counts = {
                        'pets': len(pet_ids),
                        'medical_records': MedicalRecord.all_objects.filter(
                            pet_id__in=pet_ids,
                        ).count(),
                        'appointments': appointments.count(),
                        'sales': sales.count(),
                        'statements': statements.count(),
                        'reservations': reservations.count(),
                    }

                    appointments.update(user=new_owner, branch=target_branch)
                    sales.update(
                        customer=new_owner,
                        customer_type=Sale.CustomerType.REGISTERED,
                    )
                    statements.update(customer=new_owner)
                    reservations.update(user=new_owner)
                    MedicalRecord.all_objects.filter(
                        pet_id__in=pet_ids,
                    ).update(branch=target_branch)
                    pets.update(owner=new_owner, branch=target_branch)

                    OwnerAccountLink.objects.create(
                        archived_owner=archived_owner,
                        new_owner=new_owner,
                        linked_by=request.user,
                        record_counts=record_counts,
                    )

                messages.success(
                    request,
                    f"Archived records for {archived_owner.get_full_name() or archived_owner.username} "
                    f"were linked to {new_owner.get_full_name() or new_owner.username}.",
                )
                return redirect('accounts:owner_archive')

    return render(request, 'accounts/link_archived_owner.html', {
        'archived_owner': archived_owner,
        'candidates': candidates,
        'search_query': search_query,
        'selected_owner_id': request.POST.get('new_owner_id', ''),
    })


@login_required
@admin_only
def records_archive(request):
    """List soft-deleted operational and clinical records for superadmins."""
    search_query = request.GET.get('q', '').strip()
    selected_type = request.GET.get('type', '').strip()
    selected_retention = request.GET.get('retention', '').strip()
    deleted_from = request.GET.get('deleted_from', '').strip()
    deleted_to = request.GET.get('deleted_to', '').strip()
    deleted_from_value = parse_date(deleted_from)
    deleted_to_value = parse_date(deleted_to)
    valid_types = {value for value, _ in ARCHIVE_TYPE_FILTERS}
    valid_retention_states = {value for value, _ in ARCHIVE_RETENTION_FILTERS}
    if selected_type not in valid_types:
        selected_type = ''
    if selected_retention not in valid_retention_states:
        selected_retention = ''

    now = timezone.now()
    retention_cutoff = now - timedelta(days=ARCHIVE_RETENTION_DAYS)

    def filtered_archived(model, kind):
        queryset = model.all_objects.filter(is_deleted=True)
        if selected_type and selected_type != kind:
            return queryset.none()
        if deleted_from_value:
            queryset = queryset.filter(deleted_at__date__gte=deleted_from_value)
        if deleted_to_value:
            queryset = queryset.filter(deleted_at__date__lte=deleted_to_value)
        if selected_retention == 'restorable':
            queryset = queryset.filter(deleted_at__gt=retention_cutoff)
        elif selected_retention == 'expired':
            queryset = queryset.filter(deleted_at__lte=retention_cutoff)
        return queryset

    items = []

    products = filtered_archived(Product, 'product').select_related('branch')
    services = filtered_archived(Service, 'service')
    pets = filtered_archived(Pet, 'pet').select_related('owner')
    medical_records = filtered_archived(MedicalRecord, 'medical_record').select_related('pet')
    entries = filtered_archived(RecordEntry, 'record_entry').select_related('record__pet')
    files = filtered_archived(MedicalFile, 'medical_file').select_related('record__pet')

    if search_query:
        products = products.filter(
            Q(name__icontains=search_query)
            | Q(sku__icontains=search_query)
            | Q(description__icontains=search_query)
        )
        services = services.filter(
            Q(name__icontains=search_query)
            | Q(category__icontains=search_query)
            | Q(description__icontains=search_query)
        )
        pets = pets.filter(
            Q(name__icontains=search_query)
            | Q(pet_code__icontains=search_query)
            | Q(species__icontains=search_query)
            | Q(owner__first_name__icontains=search_query)
            | Q(owner__last_name__icontains=search_query)
            | Q(guest_owner_name__icontains=search_query)
        )
        medical_records = medical_records.filter(
            Q(pet__name__icontains=search_query)
            | Q(treatment__icontains=search_query)
            | Q(history_clinical_signs__icontains=search_query)
        )
        entries = entries.filter(
            Q(record__pet__name__icontains=search_query)
            | Q(treatment__icontains=search_query)
            | Q(history_clinical_signs__icontains=search_query)
            | Q(rx__icontains=search_query)
        )
        files = files.filter(
            Q(original_name__icontains=search_query)
            | Q(record__pet__name__icontains=search_query)
        )

    for product in products:
        items.append({
            'kind': 'product',
            'label': 'Inventory item',
            'title': product.name,
            'description': f'{product.sku} · {product.branch.name}',
            'deleted_at': product.deleted_at,
            'object_id': product.pk,
        })
    for service in services:
        items.append({
            'kind': 'service',
            'label': 'Clinic service',
            'title': service.name,
            'description': service.category or service.description,
            'deleted_at': service.deleted_at,
            'object_id': service.pk,
        })
    for pet in pets:
        items.append({
            'kind': 'pet',
            'label': 'Pet / patient',
            'title': pet.name,
            'description': f'{pet.species} · {pet.owner_display_name} · {pet.pet_code}',
            'deleted_at': pet.deleted_at,
            'object_id': pet.pk,
        })
    for record in medical_records:
        items.append({
            'kind': 'medical_record',
            'label': 'Medical record',
            'title': record.pet.name,
            'description': f'Record dated {record.date_recorded:%b %d, %Y}',
            'deleted_at': record.deleted_at,
            'object_id': record.pk,
        })
    for entry in entries:
        items.append({
            'kind': 'record_entry',
            'label': 'Visit history',
            'title': entry.record.pet.name,
            'description': f'Visit dated {entry.date_recorded:%b %d, %Y} · '
            f'{entry.history_clinical_signs or entry.treatment or "Visit entry"}',
            'deleted_at': entry.deleted_at,
            'object_id': entry.pk,
        })
    for medical_file in files:
        items.append({
            'kind': 'medical_file',
            'label': 'Medical file',
            'title': medical_file.original_name,
            'description': medical_file.record.pet.name,
            'deleted_at': medical_file.deleted_at,
            'object_id': medical_file.pk,
        })

    for item in items:
        item['expires_at'] = item['deleted_at'] + timedelta(days=ARCHIVE_RETENTION_DAYS)
        item['days_remaining'] = max((item['expires_at'] - now).days, 0)
    items.sort(key=lambda item: item['deleted_at'] or now, reverse=True)
    page_obj = Paginator(items, 25).get_page(request.GET.get('page'))

    return render(request, 'accounts/records_archive.html', {
        'page_obj': page_obj,
        'archive_items': page_obj.object_list,
        'search_query': search_query,
        'selected_type': selected_type,
        'selected_retention': selected_retention,
        'deleted_from': deleted_from,
        'deleted_to': deleted_to,
        'archive_type_filters': ARCHIVE_TYPE_FILTERS,
        'archive_retention_filters': ARCHIVE_RETENTION_FILTERS,
        'archive_count': page_obj.paginator.count,
        'retention_days': ARCHIVE_RETENTION_DAYS,
    })


@login_required
@admin_only
@require_POST
def restore_archived_record(request, kind, pk):
    """Restore an archived object before its 30-day retention window expires."""
    models_by_kind = {
        'product': Product,
        'service': Service,
        'pet': Pet,
        'medical_record': MedicalRecord,
        'record_entry': RecordEntry,
        'medical_file': MedicalFile,
    }
    model = models_by_kind.get(kind)
    if model is None:
        messages.error(request, 'This archive item cannot be restored.')
        return redirect('accounts:records_archive')

    item = get_object_or_404(model.all_objects, pk=pk, is_deleted=True)
    retention_cutoff = timezone.now() - timedelta(days=ARCHIVE_RETENTION_DAYS)
    if not item.deleted_at or item.deleted_at <= retention_cutoff:
        messages.error(request, 'This item has passed its 30-day restore window.')
        return redirect('accounts:records_archive')

    if isinstance(item, (MedicalRecord, RecordEntry, MedicalFile)):
        pet_id = item.pet_id if isinstance(item, MedicalRecord) else item.record.pet_id
        pet = Pet.all_objects.get(pk=pet_id)
        if pet.is_deleted:
            pet.restore()
        if isinstance(item, (RecordEntry, MedicalFile)):
            record = MedicalRecord.all_objects.get(pk=item.record_id)
            if record.is_deleted:
                record.restore()
        item.refresh_from_db()

    if item.is_deleted:
        item.restore()
    messages.success(request, 'The archived item was restored.')
    return redirect('accounts:records_archive')