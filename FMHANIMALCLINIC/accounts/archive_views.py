"""Super-admin views for retained records of deactivated pet-owner accounts."""

from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Prefetch, Q
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import admin_only
from accounts.models import User
from appointments.models import Appointment
from billing.models import CustomerStatement, Service
from branches.models import Branch
from diagnostics.models import AIDiagnosis
from inventory.models import Product, Reservation
from patients.models import Pet
from pos.models import Sale
from records.models import MedicalFile, MedicalRecord, RecordEntry

ARCHIVE_RETENTION_DAYS = 30


@login_required
@admin_only
def owner_archive(request):
    search_query = request.GET.get('q', '').strip()
    branch_id = request.GET.get('branch', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    owners = User.objects.filter(
        owner_account_deactivated_at__isnull=False,
    ).select_related('branch').order_by('-owner_account_deactivated_at', 'last_name', 'first_name')

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
def records_archive(request):
    """List soft-deleted operational and clinical records for superadmins."""
    search_query = request.GET.get('q', '').strip()
    items = []

    products = Product.all_objects.filter(is_deleted=True).select_related('branch')
    services = Service.all_objects.filter(is_deleted=True)
    pets = Pet.all_objects.filter(is_deleted=True).select_related('owner')
    medical_records = MedicalRecord.all_objects.filter(
        is_deleted=True,
    ).select_related('pet')
    entries = RecordEntry.all_objects.filter(
        is_deleted=True,
    ).select_related('record__pet')
    files = MedicalFile.all_objects.filter(
        is_deleted=True,
    ).select_related('record__pet')

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

    now = timezone.now()
    for item in items:
        item['expires_at'] = item['deleted_at'] + timedelta(days=ARCHIVE_RETENTION_DAYS)
        item['days_remaining'] = max((item['expires_at'] - now).days, 0)
    items.sort(key=lambda item: item['deleted_at'] or now, reverse=True)
    page_obj = Paginator(items, 25).get_page(request.GET.get('page'))

    return render(request, 'accounts/records_archive.html', {
        'page_obj': page_obj,
        'archive_items': page_obj.object_list,
        'search_query': search_query,
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