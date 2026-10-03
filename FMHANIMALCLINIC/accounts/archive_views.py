"""Super-admin views for retained records of deactivated pet-owner accounts."""

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render
from django.utils.dateparse import parse_date

from accounts.decorators import admin_only
from accounts.models import User
from appointments.models import Appointment
from billing.models import CustomerStatement
from branches.models import Branch
from diagnostics.models import AIDiagnosis
from inventory.models import Reservation
from patients.models import Pet
from pos.models import Sale
from records.models import MedicalRecord


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
        pets = Pet.objects.filter(owner=owner).select_related('branch', 'clinical_status').order_by('name')
        if branch_id.isdigit():
            pets = pets.filter(branch_id=branch_id)
        pets = list(pets)
        pet_ids = [pet.pk for pet in pets]

        medical_records = MedicalRecord.objects.filter(
            pet_id__in=pet_ids,
        ).select_related('pet', 'branch', 'vet').prefetch_related(
            'entries', 'medical_files'
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
        'branches': Branch.objects.order_by('name'),
        'search_query': search_query,
        'selected_branch': branch_id,
        'date_from': date_from,
        'date_to': date_to,
        'archive_count': page_obj.paginator.count,
    })