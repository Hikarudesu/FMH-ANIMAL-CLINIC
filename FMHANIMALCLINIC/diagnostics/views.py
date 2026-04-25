"""
Views for the AI Diagnostics module.

Vet-in-the-Loop Workflow:
  Phase A: Symptom Intake & AI Generation (run_diagnosis GET/POST)
  Phase B: Vet Assessment & Selection (diagnosis_detail + review UI)
  Phase C: ORM Data Migration (mark_reviewed POST)
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator

from accounts.decorators import module_permission_required
from appointments.models import Appointment
from patients.models import Pet
from records.models import MedicalRecord, RecordEntry
from settings.models import ClinicalStatus

from .models import AIDiagnosis
from .services import get_ai_diagnosis


@login_required
@module_permission_required('ai_diagnostics', 'VIEW')
def dashboard(request):
    """AI Diagnostics dashboard - list pets, recent diagnoses."""
    # Check permissions for CRUD buttons
    can_create = request.user.has_module_permission('ai_diagnostics', 'CREATE')
    can_delete = request.user.has_module_permission('ai_diagnostics', 'DELETE')
    
    # Check if user is branch-restricted
    is_branch_restricted = request.user.is_module_branch_restricted('ai_diagnostics')
    user_branch = getattr(request.user, 'branch', None)
    
    recent_diagnoses = AIDiagnosis.objects.select_related(
        'pet', 'pet__owner', 'requested_by'
    ).order_by('-created_at')
    
    # Filter by branch if user is restricted
    if is_branch_restricted and user_branch:
        recent_diagnoses = recent_diagnoses.filter(pet__owner__branch=user_branch)
    recent_diagnoses = recent_diagnoses[:20]

    pets_query = Pet.objects.filter(is_active=True).select_related('owner')
    
    # Filter pets by branch if restricted
    if is_branch_restricted and user_branch:
        pets_query = pets_query.filter(owner__branch=user_branch)

    search = request.GET.get('search', '').strip()
    if search:
        pets_query = pets_query.filter(name__icontains=search).order_by('name')
    else:
        pets_query = pets_query.order_by('-created_at')

    paginator = Paginator(pets_query, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'diagnostics/dashboard.html', {
        'recent_diagnoses': recent_diagnoses,
        'pets': page_obj.object_list,
        'page_obj': page_obj,
        'search': search,
        'can_create': can_create,
        'can_delete': can_delete,
        'is_branch_restricted': is_branch_restricted,
    })


@login_required
@module_permission_required('ai_diagnostics', 'CREATE')
def run_diagnosis(request, pet_id):
    """
    Phase A: Symptom Intake & AI Generation.
    
    GET: Display form for symptom input
    POST: Run AI diagnosis and redirect to detail page
    """
    pet = get_object_or_404(Pet, pk=pet_id)

    # Get last 10 medical history entries
    entries = RecordEntry.objects.filter(
        record__pet=pet
    ).select_related('record').order_by('-date_recorded')[:10]

    # Get latest appointment with symptoms (if any)
    latest_appointment = Appointment.objects.filter(
        pet=pet
    ).order_by('-appointment_date', '-created_at').first()

    # Previous AI diagnoses for sidebar
    previous_diagnoses = AIDiagnosis.objects.filter(
        pet=pet
    ).order_by('-created_at')[:5]

    if request.method == 'POST':
        current_symptoms = request.POST.get('current_symptoms', '').strip()

        # Call AI service with symptoms + history
        result = get_ai_diagnosis(
            pet=pet,
            record_entries=entries,
            appointment=latest_appointment,
            additional_symptoms=current_symptoms if current_symptoms else None
        )

        # Get staff profile
        staff_member = getattr(request.user, 'staff_profile', None)

        # Create AIDiagnosis record
        diagnosis = AIDiagnosis.objects.create(
            pet=pet,
            requested_by=staff_member,
            input_symptoms=current_symptoms or (
                latest_appointment.pet_symptoms if latest_appointment else ''
            ),
            input_history=result.get('_input_history', ''),
            primary_condition=result.get('primary_diagnosis', {}).get('condition', 'Unknown'),
            primary_reasoning=result.get('primary_diagnosis', {}).get('reasoning', ''),
            differential_diagnoses=result.get('differential_diagnoses', []),
            recommended_tests=result.get('recommended_tests', []),
            warning_signs=result.get('warning_signs', []),
            summary=result.get('summary', ''),
            raw_response=result.get('_raw', None)
        )

        messages.success(request, f'AI diagnosis completed for {pet.name}.')
        return redirect('diagnostics:detail', pk=diagnosis.pk)

    return render(request, 'diagnostics/run_diagnosis.html', {
        'pet': pet,
        'entries': entries,
        'latest_appointment': latest_appointment,
        'previous_diagnoses': previous_diagnoses,
        'has_history': entries.exists() if hasattr(entries, 'exists') else bool(entries),
    })


@login_required
@module_permission_required('ai_diagnostics', 'VIEW')
def diagnosis_detail(request, pk):
    """
    Phase B: Vet Assessment & Selection UI.
    
    Display AI results with selectable conditions and tests.
    Vet can select one condition, multiple tests, and enter Rx.
    """
    diagnosis = get_object_or_404(
        AIDiagnosis.objects.select_related(
            'pet', 'requested_by', 'reviewed_by', 'linked_record_entry'
        ),
        pk=pk
    )

    # All selectable conditions (primary + differentials)
    all_conditions = diagnosis.get_all_conditions()

    # Other diagnoses for sidebar
    related_diagnoses = AIDiagnosis.objects.filter(
        pet=diagnosis.pet
    ).exclude(pk=pk).order_by('-created_at')[:5]

    # Check delete permission
    can_delete = request.user.has_module_permission('ai_diagnostics', 'DELETE')

    return render(request, 'diagnostics/detail.html', {
        'diagnosis': diagnosis,
        'all_conditions': all_conditions,
        'related_diagnoses': related_diagnoses,
        'can_delete': can_delete,
    })


@login_required
@module_permission_required('ai_diagnostics', 'VIEW')
@require_http_methods(['POST'])
def mark_reviewed(request, pk):
    """
    Phase C: ORM Data Migration (Post-Review).
    
    When vet clicks "Mark as Reviewed & Create Visit":
    1. Validate required fields (selected condition, tests, Rx)
    2. Update AIDiagnosis with selections
    3. Create RecordEntry with mapped data
    4. Signal triggers Pet.status update
    """
    diagnosis = get_object_or_404(AIDiagnosis, pk=pk)

    if diagnosis.is_reviewed:
        messages.warning(request, 'This diagnosis has already been reviewed.')
        return redirect('diagnostics:detail', pk=pk)

    # Get form data
    selected_condition = request.POST.get('selected_condition', '').strip()
    selected_tests = request.POST.getlist('selected_tests', [])
    vet_prescription = request.POST.get('vet_prescription', '').strip()

    # Validate required fields
    if not selected_condition:
        messages.error(request, 'Please select a diagnosis condition.')
        return redirect('diagnostics:detail', pk=pk)

    if not vet_prescription:
        messages.error(request, 'Please enter a prescription (Rx) before marking as reviewed.')
        return redirect('diagnostics:detail', pk=pk)

    staff_member = getattr(request.user, 'staff_profile', None)

    with transaction.atomic():
        # Update AIDiagnosis
        diagnosis.is_reviewed = True
        diagnosis.reviewed_by = staff_member
        diagnosis.reviewed_at = timezone.now()
        diagnosis.selected_condition = selected_condition
        diagnosis.selected_tests = selected_tests
        diagnosis.vet_prescription = vet_prescription

        # Get or create MedicalRecord for this pet
        medical_record = MedicalRecord.objects.filter(pet=diagnosis.pet).first()
        if not medical_record:
            medical_record = MedicalRecord.objects.create(
                pet=diagnosis.pet,
                vet=staff_member,
                branch=getattr(staff_member, 'branch', None) if staff_member else None,
                date_recorded=timezone.now().date(),
            )

        # Build history_clinical_signs
        clinical_signs_parts = []
        if diagnosis.input_symptoms:
            clinical_signs_parts.append(f"Presenting Symptoms:\n{diagnosis.input_symptoms}")
        clinical_signs_parts.append(f"Diagnosis: {selected_condition}")
        history_clinical_signs = '\n\n'.join(clinical_signs_parts)

        # Build treatment field from selected tests
        treatment = ''
        if selected_tests:
            treatment = "Recommended Tests:\n" + '\n'.join(f"• {test}" for test in selected_tests)

        diagnostics_status = ClinicalStatus.objects.filter(code='DIAGNOSTICS').first() or ClinicalStatus.get_default()

        # Create RecordEntry
        record_entry = RecordEntry.objects.create(
            record=medical_record,
            vet=staff_member,
            date_recorded=timezone.now().date(),
            history_clinical_signs=history_clinical_signs,
            treatment=treatment,
            rx=vet_prescription,
            action_required=diagnostics_status,
        )

        # Link diagnosis to record entry
        diagnosis.linked_record_entry = record_entry
        diagnosis.save()

    messages.success(
        request,
        f'Diagnosis reviewed and visit record created for {diagnosis.pet.name}.'
    )
    return redirect('diagnostics:detail', pk=pk)


@login_required
@module_permission_required('ai_diagnostics', 'VIEW')
def pet_diagnosis_history(request, pet_id):
    """JSON API: Get diagnosis history for a pet."""
    pet = get_object_or_404(Pet, pk=pet_id)
    diagnoses = AIDiagnosis.objects.filter(pet=pet).order_by('-created_at')[:20]

    return JsonResponse({
        'pet': {'id': pet.id, 'name': pet.name},
        'diagnoses': [
            {
                'id': d.id,
                'primary_condition': d.primary_condition,
                'summary': d.summary,
                'created_at': d.created_at.isoformat(),
                'is_reviewed': d.is_reviewed,
            }
            for d in diagnoses
        ]
    })


@login_required
@module_permission_required('ai_diagnostics', 'DELETE')
@require_http_methods(['POST'])
def delete_diagnosis(request, pk):
    """
    Delete an AI diagnosis.
    
    Note: The linked medical record (if any) is NOT deleted - 
    the ForeignKey uses SET_NULL, so the record entry remains intact.
    """
    diagnosis = get_object_or_404(AIDiagnosis, pk=pk)
    pet_name = diagnosis.pet.name
    
    # Store info before deletion
    was_reviewed = diagnosis.is_reviewed
    had_linked_record = diagnosis.linked_record_entry is not None
    
    # Delete the diagnosis (linked_record_entry will be set to NULL, not deleted)
    diagnosis.delete()
    
    if was_reviewed and had_linked_record:
        messages.success(
            request,
            f'AI diagnosis for {pet_name} deleted. The linked medical record entry was preserved.'
        )
    else:
        messages.success(request, f'AI diagnosis for {pet_name} deleted.')
    
    return redirect('diagnostics:dashboard')
