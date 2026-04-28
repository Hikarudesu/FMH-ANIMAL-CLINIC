"""
Views for handling specific actions within Medical Records.
"""
# pylint: disable=no-member
import io
import json

from xhtml2pdf import pisa

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.staticfiles import finders
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils import timezone

from accounts.decorators import module_permission_required
from patients.models import Pet  # pylint: disable=no-member
from branches.models import Branch
from employees.models import StaffMember
from FMHANIMALCLINIC.form_mixins import validate_philippines_phone
from settings.models import ClinicalStatus, ClinicProfile
from .models import MedicalRecord, RecordEntry
from .forms import MedicalRecordForm, RecordEntryForm

User = get_user_model()


def get_veterinarians_for_json():
    """
    Get active veterinarian StaffMember profiles for vet dropdowns.
    Also auto-creates missing staff profiles from veterinarian User accounts
    so medical record vet FK options stay in sync with RBAC user roles.
    """
    from accounts.rbac_models import Role

    vet_role_codes = {Role.VET}
    vet_role_names = {'veterinarian'}

    vet_users = User.objects.filter(
        is_active=True,
        assigned_role__isnull=False,
    ).select_related('assigned_role', 'branch').order_by('last_name', 'first_name')

    for user in vet_users:
        role = user.assigned_role
        if not role:
            continue
        role_code = (role.code or '').lower()
        role_name = (role.name or '').lower()
        is_vet_role = role_code in vet_role_codes or any(name in role_name for name in vet_role_names)
        if not is_vet_role:
            continue

        staff_profile, _ = StaffMember.objects.get_or_create(
            user=user,
            defaults={
                'first_name': user.first_name or user.username,
                'last_name': user.last_name or '',
                'email': user.email or '',
                'phone': user.phone_number or '',
                'branch': user.branch,
                'position': StaffMember.Position.VETERINARIAN,
                'is_active': user.is_active,
            },
        )

        update_fields = []
        if staff_profile.position != StaffMember.Position.VETERINARIAN:
            staff_profile.position = StaffMember.Position.VETERINARIAN
            update_fields.append('position')
        if staff_profile.branch_id != user.branch_id:
            staff_profile.branch = user.branch
            update_fields.append('branch')
        if staff_profile.is_active != user.is_active:
            staff_profile.is_active = user.is_active
            update_fields.append('is_active')
        if update_fields:
            staff_profile.save(update_fields=update_fields)

    vets = StaffMember.objects.filter(
        position='VETERINARIAN', is_active=True
    ).select_related('branch').order_by('last_name', 'first_name')
    
    vets_for_json = [
        {'id': v.id, 'name': f'Dr. {v.first_name} {v.last_name}',
         'branch_id': v.branch_id, 'license_number': v.license_number or ''}
        for v in vets
    ]
    
    return vets, vets_for_json


@login_required
@module_permission_required('medical_records', 'VIEW')
def admin_records_list(request):
    """View to list all medical records for admin/staff in the portal."""
    
    # Check if user is branch-restricted
    is_branch_restricted = request.user.is_module_branch_restricted('medical_records')
    user_branch = getattr(request.user, 'branch', None)

    query = request.GET.get('q', '')
    records = MedicalRecord.objects.all().select_related(
        'pet', 'pet__owner', 'vet', 'branch'
    ).prefetch_related('entries')
    
    # Apply branch restriction first if user is restricted
    if is_branch_restricted and user_branch:
        records = records.filter(branch=user_branch)

    if query:
        records = records.filter(
            Q(pet__name__icontains=query) |
            Q(pet__owner__first_name__icontains=query) |
            Q(pet__owner__last_name__icontains=query) |
            Q(pet__species__icontains=query) |
            Q(pet__breed__icontains=query) |
            Q(entries__history_clinical_signs__icontains=query) |
            Q(entries__treatment__icontains=query) |
            Q(entries__rx__icontains=query) |
            Q(branch__name__icontains=query)
        ).distinct()

    # Branch filter (only if user is not restricted)
    branch_id = request.GET.get('branch', '')
    if branch_id and not is_branch_restricted:
        records = records.filter(branch_id=branch_id)

    # Vet filter
    vet_id = request.GET.get('vet', '')
    if vet_id:
        records = records.filter(vet_id=vet_id)

    # Source filter
    source = request.GET.get('source', '')
    if source:
        records = records.filter(pet__source=source)

    branches = Branch.objects.filter(
        is_active=True)  # pylint: disable=no-member
    vets, _ = get_veterinarians_for_json()

    # Pagination
    page_number = request.GET.get('page', 1)
    paginator = Paginator(records, 10)
    page_obj = paginator.get_page(page_number)

    # Pre-compute which records have missing fields (for warning icon + PDF blocking)
    record_warnings = {}
    for rec in page_obj:
        missing = get_record_missing_fields(rec, rec.entries.all())
        record_warnings[rec.pk] = bool(missing)

    # Check permissions for CRUD buttons
    can_create = request.user.has_module_permission('medical_records', 'CREATE')
    can_edit = request.user.has_module_permission('medical_records', 'EDIT')
    can_delete = request.user.has_module_permission('medical_records', 'DELETE')

    context = {
        'records': page_obj,
        'page_obj': page_obj,
        'search_query': query,
        'branches': [] if is_branch_restricted else branches,
        'selected_branch': branch_id,
        'vets': vets,
        'selected_vet': vet_id,
        'source_choices': Pet.Source.choices,
        'selected_source': source,
        'record_warnings': record_warnings,
        'can_create': can_create,
        'can_edit': can_edit,
        'can_delete': can_delete,
        'is_branch_restricted': is_branch_restricted,
    }
    return render(request, 'records/admin_list.html', context)


@login_required
@module_permission_required('medical_records', 'CREATE')
def admin_record_create(request):
    """View to create a new visit entry, reusing the pet's existing record card if one exists."""

    if request.method == 'POST':
        entry_form = RecordEntryForm(request.POST)
        if entry_form.is_valid():

            client_source = request.POST.get('client_source', 'PORTAL').strip()
            owner_name_str = request.POST.get('owner_name', '').strip()
            owner_contact = request.POST.get('owner_contact', '').strip()
            owner_address = request.POST.get('owner_address', '').strip()
            selected_user_id = request.POST.get('selected_user_id', '').strip()

            # Validate phone number using centralized function
            if owner_contact:
                try:
                    validate_philippines_phone(owner_contact)
                except Exception as e:
                    entry_form.add_error(None, str(e))

            if not entry_form.errors:
                # --- Dynamic Owner / Guest Resolution ---
                owner = None
                if client_source == 'WALKIN':
                    # Walk-in: no User account — guest info stored on Pet
                    pass
                elif selected_user_id:
                    # Portal: look up the selected registered user by ID (pet owner = not staff)
                    try:
                        owner = User.objects.filter(
                            Q(assigned_role__is_staff_role=False) | Q(assigned_role__isnull=True)
                        ).get(pk=int(selected_user_id))
                        if owner_contact:
                            owner.phone_number = owner_contact
                        if owner_address:
                            owner.address = owner_address
                        owner.save()
                    except (User.DoesNotExist, ValueError):
                        entry_form.add_error(
                            None,
                            "Selected owner not found. Please select a valid registered owner.",
                        )
                elif client_source == 'PORTAL':
                    entry_form.add_error(
                        None,
                        "Please select an owner from the registered users list.",
                    )

                if not entry_form.errors:
                    # --- Dynamic Pet Resolution or Creation ---
                    pet_name_str = request.POST.get('pet_name', '').strip()
                    pet = None

                    if client_source == 'WALKIN' and pet_name_str:
                        # Walk-in: look up pet by name + guest owner name
                        pet_qs = Pet.objects.filter(  # pylint: disable=no-member
                            name__iexact=pet_name_str,
                            source=Pet.Source.WALKIN,
                            guest_owner_name__iexact=owner_name_str,
                        )
                        if pet_qs.exists():
                            pet = pet_qs.first()
                        else:
                            pet = Pet(name=pet_name_str, source=Pet.Source.WALKIN)
                        pet.guest_owner_name = owner_name_str
                        pet.guest_owner_phone = owner_contact
                        pet.guest_owner_address = owner_address
                    elif pet_name_str and owner:
                        pet_qs = Pet.objects.filter(  # pylint: disable=no-member
                            name__iexact=pet_name_str, owner=owner)
                        if pet_qs.exists():
                            pet = pet_qs.first()
                        else:
                            pet = Pet(name=pet_name_str, owner=owner)
                        pet.source = Pet.Source.PORTAL

                    if pet:
                        if 'pet_color' in request.POST:
                            pet.color = request.POST.get('pet_color')
                        if 'pet_breed' in request.POST:
                            pet.breed = request.POST.get('pet_breed')
                        if 'pet_species' in request.POST:
                            pet.species = request.POST.get('pet_species')

                        pet_age_str = request.POST.get('pet_age', '')
                        if pet_age_str:
                            from datetime import date as _d
                            try:
                                pet.date_of_birth = _d.fromisoformat(pet_age_str.strip())
                            except ValueError:
                                pass

                        pet_sex_str = request.POST.get('pet_sex', '').strip().upper()
                        if pet_sex_str == "FEMALE":
                            pet.sex = "FEMALE"
                        elif pet_sex_str == "MALE":
                            pet.sex = "MALE"

                        pet.save()

                    if pet:
                        # Get the most recent existing record card for this pet,
                        # or create a brand-new one — no duplicate cards.
                        branch_id = request.POST.get('branch')
                        record = MedicalRecord.objects.filter(pet=pet).order_by('-created_at').first()

                        # Get vet from the form (RecordEntryForm now includes vet field)
                        selected_vet = entry_form.cleaned_data.get('vet')

                        # Fall back to logged-in user if no vet selected
                        if not selected_vet and hasattr(request.user, 'staffmember'):
                            selected_vet = request.user.staffmember

                        if not record:
                            record = MedicalRecord(
                                pet=pet,
                                date_recorded=entry_form.cleaned_data['date_recorded'],
                                weight=entry_form.cleaned_data.get('weight'),
                                temperature=entry_form.cleaned_data.get('temperature'),
                                history_clinical_signs=entry_form.cleaned_data.get('history_clinical_signs') or '',
                                treatment=entry_form.cleaned_data.get('treatment') or '',
                                rx=entry_form.cleaned_data.get('rx') or '',
                                lab_results=entry_form.cleaned_data.get('lab_results') or '',
                                ff_up=entry_form.cleaned_data.get('ff_up'),
                            )
                            if selected_vet:
                                record.vet = selected_vet
                            if branch_id:
                                try:
                                    record.branch = Branch.objects.get(pk=branch_id)
                                except (Branch.DoesNotExist, ValueError):
                                    pass
                            record.save()
                        else:
                            # Update record card with latest data from this entry
                            update_fields = []
                            if branch_id:
                                try:
                                    record.branch = Branch.objects.get(pk=branch_id)
                                    update_fields.append('branch')
                                except (Branch.DoesNotExist, ValueError):
                                    pass
                            if selected_vet:
                                record.vet = selected_vet
                                update_fields.append('vet')

                            # Update medical data fields to reflect latest entry
                            record.date_recorded = entry_form.cleaned_data['date_recorded']
                            record.weight = entry_form.cleaned_data.get('weight')
                            record.temperature = entry_form.cleaned_data.get('temperature')
                            record.history_clinical_signs = entry_form.cleaned_data.get('history_clinical_signs') or ''
                            record.treatment = entry_form.cleaned_data.get('treatment') or ''
                            record.rx = entry_form.cleaned_data.get('rx') or ''
                            record.lab_results = entry_form.cleaned_data.get('lab_results') or ''
                            record.ff_up = entry_form.cleaned_data.get('ff_up')
                            update_fields.extend(['date_recorded', 'weight', 'temperature', 'history_clinical_signs', 'treatment', 'rx', 'lab_results', 'ff_up'])

                            record.save(update_fields=update_fields if update_fields else None)

                        # Always create a new entry (visit row) on the record card
                        entry = entry_form.save(commit=False)
                        entry.record = record
                        # The vet is already set from the form
                        # But if the form had no vet and we have selected_vet fallback, use it
                        if not entry.vet and selected_vet:
                            entry.vet = selected_vet
                        entry.save()

                        messages.success(
                            request,
                            f'Visit entry added to {pet.name}\'s medical record.'
                        )
                        return redirect('records:admin_detail', pk=record.pk)
                    else:
                        entry_form.add_error(
                            None,
                            "Could not resolve or create patient profile. "
                            "Ensure Owner and Pet names are provided.",
                        )
    else:
        initial_data = {'date_recorded': timezone.now().date()}
        entry_form = RecordEntryForm(initial=initial_data)

    # Build pet details JSON for dynamic form population
    pets = Pet.objects.select_related('owner').all()  # pylint: disable=no-member
    pets_data = {}
    for p in pets:
        last_record = p.medical_records.filter(
            branch__isnull=False
        ).order_by('-date_recorded').first()

        # Handle both portal and walk-in pets
        if p.owner:
            owner_name = p.owner.get_full_name() or p.owner.username
            owner_address = p.owner.address
            owner_contact = p.owner.phone_number
            branch_id = p.owner.branch_id or (last_record.branch_id if last_record else '')
        else:
            # Walk-in patient
            owner_name = p.guest_owner_name
            owner_address = p.guest_owner_address
            owner_contact = p.guest_owner_phone
            branch_id = last_record.branch_id if last_record else ''

        pets_data[p.name] = {
            'owner_id': p.owner_id or '',
            'owner_name': owner_name,
            'owner_address': owner_address,
            'owner_contact': owner_contact,
            'date_of_birth': p.date_of_birth.isoformat() if p.date_of_birth else '',
            'pet_color': p.color,
            'pet_species': p.species,
            'pet_breed': p.breed,
            'pet_sex': p.get_sex_display(),
            'branch_id': branch_id,
            'source': p.source,
        }

    branches = Branch.objects.filter(is_active=True)  # pylint: disable=no-member
    vets, vets_for_json = get_veterinarians_for_json()
    
    context = {
        'form': entry_form,
        'pets_data': pets_data,
        'pets_json': json.dumps(pets_data),
        'branches': branches,
        'vets': vets,
        'vets_json': json.dumps(vets_for_json),
    }
    return render(request, 'records/admin_form.html', context)


@login_required
@module_permission_required('medical_records', 'EDIT')
def admin_record_edit(request, pk):
    """View to edit an existing medical record."""

    record = get_object_or_404(MedicalRecord, pk=pk)

    if request.method == 'POST':
        form = MedicalRecordForm(request.POST, instance=record)
        if form.is_valid():
            # Validate phone number using centralized function
            owner_contact_val = request.POST.get('owner_contact', '').strip()
            if owner_contact_val:
                try:
                    validate_philippines_phone(owner_contact_val)
                except Exception as e:
                    form.add_error(None, str(e))

            if not form.errors:
                updated_record = form.save(commit=False)

                # --- Update Owner details if provided ---
                owner_name_str = request.POST.get('owner_name', '').strip()
                if owner_name_str:
                    parts = owner_name_str.split(' ', 1)
                    first_name = parts[0]
                    last_name = parts[1] if len(parts) > 1 else ''
                    owner_qs = User.objects.filter(
                        first_name=first_name,
                        last_name=last_name,
                    ).filter(
                        Q(assigned_role__is_staff_role=False) | Q(assigned_role__isnull=True)
                    )
                    if owner_qs.exists():
                        owner = owner_qs.first()
                        if 'owner_contact' in request.POST:
                            owner.phone_number = request.POST.get('owner_contact')
                        if 'owner_address' in request.POST:
                            owner.address = request.POST.get('owner_address')
                        owner.save()

                # --- Update Pet details if provided ---
                pet = record.pet
                if 'pet_color' in request.POST:
                    pet.color = request.POST.get('pet_color')
                if 'pet_breed' in request.POST:
                    pet.breed = request.POST.get('pet_breed')
                if 'pet_species' in request.POST:
                    pet.species = request.POST.get('pet_species')

                pet_age_str = request.POST.get('pet_age', '')
                if pet_age_str:
                    from datetime import date as _d
                    try:
                        pet.date_of_birth = _d.fromisoformat(pet_age_str.strip())
                    except ValueError:
                        pass

                pet_sex_str = request.POST.get('pet_sex', '').strip().upper()
                if pet_sex_str == "FEMALE":
                    pet.sex = "FEMALE"
                elif pet_sex_str == "MALE":
                    pet.sex = "MALE"

                pet.save()
                updated_record.save()
                
                # Sync edits down to the latest RecordEntry so that the UI correctly updates 
                # for the admin_list and medical record detail page.
                latest_entry = RecordEntry.objects.filter(
                    record=updated_record
                ).order_by('-date_recorded', '-created_at').first()
                if latest_entry:
                    latest_entry.date_recorded = form.cleaned_data.get('date_recorded')
                    latest_entry.weight = form.cleaned_data.get('weight')
                    latest_entry.temperature = form.cleaned_data.get('temperature')
                    latest_entry.history_clinical_signs = form.cleaned_data.get('history_clinical_signs') or ''
                    latest_entry.treatment = form.cleaned_data.get('treatment') or ''
                    latest_entry.rx = form.cleaned_data.get('rx') or ''
                    latest_entry.lab_results = form.cleaned_data.get('lab_results') or ''
                    latest_entry.ff_up = form.cleaned_data.get('ff_up')
                    if getattr(updated_record, 'vet', None):
                        latest_entry.vet = updated_record.vet
                    latest_entry.save()
                
                messages.success(
                    request, f'Record for {record.pet.name} has been updated!')
                return redirect('records:admin_detail', pk=record.pk)
    else:
        form = MedicalRecordForm(instance=record)

    # Build pet details JSON for dynamic form population
    pets = Pet.objects.select_related(
        'owner').all()  # pylint: disable=no-member
    pets_data = {}
    for p in pets:
        last_record = p.medical_records.filter(
            branch__isnull=False
        ).order_by('-date_recorded').first()

        # Handle both portal and walk-in pets
        if p.owner:
            owner_name = p.owner.get_full_name() or p.owner.username
            owner_address = p.owner.address
            owner_contact = p.owner.phone_number
            branch_id = p.owner.branch_id or (last_record.branch_id if last_record else '')
        else:
            # Walk-in patient
            owner_name = p.guest_owner_name
            owner_address = p.guest_owner_address
            owner_contact = p.guest_owner_phone
            branch_id = last_record.branch_id if last_record else ''

        pets_data[p.name] = {
            'owner_name': owner_name,
            'owner_address': owner_address,
            'owner_contact': owner_contact,
            'date_of_birth': p.date_of_birth.isoformat() if p.date_of_birth else '',
            'pet_color': p.color,
            'pet_species': p.species,
            'pet_breed': p.breed,
            'pet_sex': p.get_sex_display(),
            'branch_id': branch_id,
        }

    vets, vets_for_json = get_veterinarians_for_json()

    context = {
        'form': form,
        'record': record,
        'pets_data': pets_data,
        'pets_json': json.dumps(pets_data),
        'branches': Branch.objects.filter(is_active=True),
        'vets': vets,
        'vets_json': json.dumps(vets_for_json),
    }
    return render(request, 'records/admin_edit_form.html', context)


@login_required
@module_permission_required('medical_records', 'DELETE')
def admin_record_delete(request, pk):
    """View to delete a medical record. Handles POST from modal on list page."""

    record = get_object_or_404(MedicalRecord, pk=pk)

    if request.method == 'POST':
        pet_name = record.pet.name
        record.delete()
        messages.success(
            request, f'Medical record for {pet_name} has been deleted.')
        return redirect('records:admin_list')

    # Redirect to list if accessed directly with GET (modal is on list page)
    return redirect('records:admin_list')


@login_required
def admin_record_detail(request, pk):
    """View to display a medical record card with all its visit entries."""

    record = get_object_or_404(MedicalRecord, pk=pk)
    entries = record.entries.order_by('date_recorded', 'created_at')

    # Check for missing details (excluding follow-up)
    missing_fields = get_record_missing_fields(record, entries)
    vets, vets_for_json = get_veterinarians_for_json()
    branches = Branch.objects.filter(is_active=True)
    clinic_profile = ClinicProfile.get_instance()
    from_patients = request.GET.get('from_patients', '0') == '1'
    active_tab = 'patients' if from_patients else 'medical_records'

    return render(request, 'records/admin_detail.html', {
        'record': record,
        'entries': entries,
        'missing_fields': missing_fields,
        'generated_date': timezone.now(),
        'vets': vets,
        'branches': branches,
        'vets_json': json.dumps(vets_for_json),
        'clinical_statuses': ClinicalStatus.objects.filter(is_active=True).order_by('order', 'name'),
        'clinic_profile': clinic_profile,
        'from_patients': from_patients,
        'active_tab': active_tab,
    })


@login_required
@module_permission_required('medical_records', 'CREATE')
def admin_add_entry(request, pk):
    """Add a new visit entry to an existing medical record card."""

    record = get_object_or_404(MedicalRecord, pk=pk)

    if request.method == 'POST':
        form = RecordEntryForm(request.POST)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.record = record
            # Update record branch if a different branch was selected
            branch_id_post = request.POST.get('branch_id', '').strip()
            if branch_id_post:
                try:
                    record.branch = Branch.objects.get(pk=branch_id_post)
                except Branch.DoesNotExist:
                    pass

            # Get vet from form, fall back to logged-in user if not set
            selected_vet = entry.vet
            if not selected_vet and hasattr(request.user, 'staffmember'):
                selected_vet = request.user.staffmember
                entry.vet = selected_vet

            if selected_vet:
                record.vet = selected_vet  # keep record banner in sync

            entry.save()

            # Keep the card-level summary fields aligned to the latest visit entry.
            record.date_recorded = entry.date_recorded
            record.weight = entry.weight
            record.temperature = entry.temperature
            record.history_clinical_signs = entry.history_clinical_signs or ''
            record.treatment = entry.treatment or ''
            record.rx = entry.rx or ''
            record.lab_results = entry.lab_results or ''
            record.ff_up = entry.ff_up
            # Touch the parent record so updated_at changes (also saves branch/vet update)
            record.save()

            messages.success(
                request, f'New visit entry added to {record.pet.name}\'s record.')
            return redirect('records:admin_detail', pk=record.pk)
    else:
        # Pre-fill with record's vet and current date
        initial_data = {
            'date_recorded': timezone.now().date(),
        }
        if record.vet:
            initial_data['vet'] = record.vet
        form = RecordEntryForm(initial=initial_data)

    vets, vets_for_json = get_veterinarians_for_json()
    branches = Branch.objects.filter(is_active=True)

    return render(request, 'records/admin_add_entry.html', {
        'form': form,
        'record': record,
        'vets': vets,
        'branches': branches,
        'vets_json': json.dumps(vets_for_json),
    })


@login_required
@module_permission_required('medical_records', 'EDIT')
def admin_entry_edit(request, entry_pk):
    """Edit a specific visit entry."""

    entry = get_object_or_404(RecordEntry, pk=entry_pk)
    record = entry.record

    if request.method == 'POST':
        form = RecordEntryForm(request.POST, instance=entry)
        if form.is_valid():
            updated_entry = form.save(commit=False)
            # The vet is now handled by the form
            updated_entry.save()

            # Sync the parent record's vet with the entry's vet
            if updated_entry.vet:
                record.vet = updated_entry.vet

            # Update record branch if a different branch was selected
            # (Branch is on the parent MedicalRecord, not on RecordEntry)
            branch_id_post = request.POST.get('branch_id', '').strip()
            if branch_id_post:
                try:
                    record.branch = Branch.objects.get(pk=branch_id_post)
                except Branch.DoesNotExist:
                    pass
            # Touch the parent record so updated_at changes
            record.save()

            messages.success(request, 'Visit entry updated.')
            return redirect('records:admin_detail', pk=record.pk)
    else:
        form = RecordEntryForm(instance=entry)

    return render(request, 'records/admin_entry_edit.html', {
        'form': form,
        'entry': entry,
        'record': record,
    })


@login_required
@module_permission_required('medical_records', 'DELETE')
def admin_entry_delete(request, entry_pk):
    """Delete a specific visit entry."""

    entry = get_object_or_404(RecordEntry, pk=entry_pk)
    record = entry.record

    if request.method == 'POST':
        entry.delete()
        # Touch the parent record so updated_at changes
        record.save()
        messages.success(request, 'Visit entry deleted.')
        return redirect('records:admin_detail', pk=record.pk)

    return render(request, 'records/admin_entry_confirm_delete.html', {
        'entry': entry,
        'record': record,
    })


def get_record_missing_fields(record, entries):
    """
    Check for missing details in the medical record and its entries.
    Returns a list of warning messages. Follow-up is excluded from checks.
    """
    warnings = []
    pet = record.pet
    owner = pet.owner

    # Owner checks (only if owner exists - not for walk-in patients)
    if owner:
        if not owner.get_full_name().strip():
            warnings.append('Owner name is missing.')
        if not getattr(owner, 'phone_number', None):
            warnings.append('Owner contact number is missing.')
        if not getattr(owner, 'address', None):
            warnings.append('Owner address is missing.')
    else:
        # Walk-in patient - check guest owner info
        if not pet.guest_owner_name:
            warnings.append('Guest owner name is missing.')
        if not pet.guest_owner_phone:
            warnings.append('Guest owner contact number is missing.')
        if not pet.guest_owner_address:
            warnings.append('Guest owner address is missing.')

    # Pet checks
    if not pet.name:
        warnings.append('Pet name is missing.')
    if not getattr(pet, 'species', None):
        warnings.append('Pet species is missing.')
    if not getattr(pet, 'breed', None):
        warnings.append('Pet breed is missing.')
    if not getattr(pet, 'sex', None):
        warnings.append('Pet sex is missing.')
    if not getattr(pet, 'color', None):
        warnings.append('Pet color is missing.')
    if not getattr(pet, 'date_of_birth', None):
        warnings.append('Pet date of birth is missing.')

    # Branch check
    if not record.branch:
        warnings.append('Branch is missing.')

    # Vet check
    if not record.vet:
        warnings.append('Attending veterinarian is missing.')

    # Entry checks (excluding follow-up)
    for i, entry in enumerate(entries, 1):
        if not entry.weight:
            warnings.append(f'Visit entry #{i}: Weight is missing.')
        if not entry.temperature:
            warnings.append(f'Visit entry #{i}: Temperature is missing.')
        if not entry.history_clinical_signs:
            warnings.append(f'Visit entry #{i}: History/Clinical Signs is missing.')
        if not entry.treatment:
            warnings.append(f'Visit entry #{i}: Treatment is missing.')
        if not entry.rx:
            warnings.append(f'Visit entry #{i}: Prescription (Rx) is missing.')

    return warnings


@login_required
@module_permission_required('medical_records', 'VIEW')
def api_search_owners(request):
    """API endpoint to search for pet owners by name (portal only)."""
    query = request.GET.get('q', '').strip()

    if not query:
        return JsonResponse({'owners': []})

    # If q=__all__, return all registered pet owners (not staff or no role)
    if query == '__all__':
        owners = User.objects.filter(
            Q(assigned_role__is_staff_role=False) | Q(assigned_role__isnull=True)
        ).order_by('first_name', 'last_name')
    else:
        if len(query) < 2:
            return JsonResponse({'owners': []})
        # Search for pet owners (not staff) by first_name or last_name
        owners = User.objects.filter(
            Q(assigned_role__is_staff_role=False) | Q(assigned_role__isnull=True)
        ).filter(
            Q(first_name__icontains=query) | Q(last_name__icontains=query)
        ).order_by('first_name', 'last_name')[:20]  # Limit to 20 results

    data = [{
        'id': owner.id,
        'full_name': owner.get_full_name() or owner.username,
        'first_name': owner.first_name,
        'last_name': owner.last_name,
        'phone_number': owner.phone_number or '',
        'address': owner.address or '',
    } for owner in owners]

    return JsonResponse({'owners': data})


def _pdf_link_callback(uri, rel):
    """
    Resolve static file URIs to absolute filesystem paths so xhtml2pdf
    can load CSS/image assets during PDF generation.
    """
    static_url = settings.STATIC_URL  # e.g. 'static/'
    if uri.startswith(static_url):
        relative = uri[len(static_url):]
        path = finders.find(relative)
        if path:
            return path
    return uri


@login_required
def download_pdf_view(request, pk):
    """
    Generate and download a PDF version of the medical record with QR code.
    """
    record = get_object_or_404(MedicalRecord, pk=pk)

    # Security: Only allow pet's owner or staff to download
    if not request.user.is_clinic_staff() and record.pet.owner != request.user:
        return HttpResponseForbidden("You do not have permission to download this record.")

    entries = record.entries.order_by('date_recorded', 'created_at')

    # Block PDF download if there are missing details (excluding follow-up)
    missing_fields = get_record_missing_fields(record, entries)
    if missing_fields:
        return JsonResponse({
            'error': 'Cannot download PDF. Please complete all required fields first.',
            'missing_fields': missing_fields,
        }, status=400)

    clinic_profile = ClinicProfile.get_instance()

    # Render HTML template
    html_content = render_to_string('records/pdf_record.html', {
        'record': record,
        'entries': entries,
        'generated_date': timezone.now(),
        'is_admin': request.user.is_clinic_staff(),
        'clinic_profile': clinic_profile,
    })

    # Generate PDF using xhtml2pdf
    result = io.BytesIO()
    pdf = pisa.pisaDocument(
        io.BytesIO(html_content.encode('UTF-8')),
        result,
        link_callback=_pdf_link_callback,
    )
    
    if pdf.err:
        return HttpResponse('Error generating PDF', status=500)

    # Create response
    response = HttpResponse(result.getvalue(), content_type='application/pdf')
    filename = f"medical_record_{record.pet.name}_{record.date_recorded}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response


@login_required
def user_record_detail(request, pk):
    """
    User-facing detail view for a single medical record.
    Only accessible by the pet's owner.
    """
    record = get_object_or_404(MedicalRecord, pk=pk)

    if record.pet.owner != request.user:
        return HttpResponseForbidden("You do not have permission to view this record.")

    entries = record.entries.order_by('date_recorded', 'created_at')
    missing_fields = get_record_missing_fields(record, entries)
    clinic_profile = ClinicProfile.get_instance()

    return render(request, 'records/user_detail.html', {
        'record': record,
        'entries': entries,
        'missing_fields': missing_fields,
        'generated_date': timezone.now(),
        'clinic_profile': clinic_profile,
    })
