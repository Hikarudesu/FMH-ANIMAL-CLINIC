"""Views for settings."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from accounts.decorators import module_permission_required, admin_only
from accounts.models import User, ActivityLog
from branches.models import Branch

from .models import (
    ClinicProfile, SystemSetting, SectionContent,
    HeroStat, CoreValue, Service, Veterinarian,
    ReasonForVisit, ClinicalStatus
)
from .forms import (
    ClinicInfoForm,
    AppointmentSettingsForm,
    InventorySettingsForm,
    NotificationSettingsForm,
    PayrollSettingsForm,
    SystemSettingsForm,
    MedicalRecordsSettingsForm,
    HeroSectionForm,
    MissionVisionForm,
    ServicesIntroForm,
    VetsIntroForm,
    HeroStatForm,
    CoreValueForm,
    ServiceForm,
    VeterinarianForm,
    ReasonForVisitForm,
    ClinicalStatusForm,
)
from .utils import set_setting


# Tab definitions for the settings page
SETTINGS_TABS = [
    {'id': 'clinic', 'label': 'Clinic Info', 'icon': 'bx-building'},
    {'id': 'scheduling', 'label': 'Scheduling & Clinical', 'icon': 'bx-calendar-check'},
    {'id': 'inventory', 'label': 'Inventory', 'icon': 'bx-package'},
    {'id': 'notifications', 'label': 'Notifications', 'icon': 'bx-bell'},
    {'id': 'payroll', 'label': 'Payroll', 'icon': 'bx-money'},
    {'id': 'system', 'label': 'System', 'icon': 'bx-cog'},
    {'id': 'content', 'label': 'Content Management', 'icon': 'bx-edit'},
]


@login_required
@admin_only
@module_permission_required('settings', 'MANAGE')
def settings_main(request, default_tab=None):
    """Main settings view with tabbed interface."""

    active_tab = request.GET.get('tab', default_tab or 'clinic')

    # Validate tab
    valid_tabs = [t['id'] for t in SETTINGS_TABS]
    if active_tab not in valid_tabs:
        active_tab = 'clinic'

    # Get clinic profile for the form
    clinic_profile = ClinicProfile.get_instance()

    # Handle POST requests
    if request.method == 'POST':
        form_type = request.POST.get('form_type')

        if form_type == 'clinic':
            return _handle_clinic_form(request, clinic_profile)
        elif form_type == 'appointments':
            return _handle_appointments_form(request)
        elif form_type == 'inventory':
            return _handle_inventory_form(request)
        elif form_type == 'notifications':
            return _handle_notifications_form(request)
        elif form_type == 'payroll':
            return _handle_payroll_form(request)
        elif form_type == 'system':
            return _handle_system_form(request)
        elif form_type == 'medical':
            return _handle_medical_form(request)
        elif form_type == 'content':
            return _handle_content_form(request)
        elif form_type == 'reason_for_visit':
            return _handle_reason_for_visit_form(request)
        elif form_type == 'clinical_status':
            return _handle_clinical_status_form(request)
        elif form_type == 'delete_reason':
            return _handle_delete_reason(request)
        elif form_type == 'delete_status':
            return _handle_delete_status(request)

    # Initialize all forms for GET request
    forms_dict = {
        'clinic': ClinicInfoForm(instance=clinic_profile),
        'scheduling': {
            'appointments': AppointmentSettingsForm(),
            'medical': MedicalRecordsSettingsForm(),
            'reasons': ReasonForVisit.objects.all(),
            'statuses': ClinicalStatus.objects.all(),
            'reason_form': ReasonForVisitForm(),
            'status_form': ClinicalStatusForm(),
        },
        'inventory': InventorySettingsForm(),
        'notifications': NotificationSettingsForm(),
        'payroll': PayrollSettingsForm(),
        'system': SystemSettingsForm(),
        'content': _get_content_forms(),
    }

    context = {
        'forms': forms_dict,
        'active_tab': active_tab,
        'tabs': SETTINGS_TABS,
        'clinic_profile': clinic_profile,
    }

    return render(request, 'settings/settings_main.html', context)


def _handle_clinic_form(request, clinic_profile):
    """Handle clinic info form submission."""
    form = ClinicInfoForm(request.POST, request.FILES, instance=clinic_profile)
    if form.is_valid():
        form.save()
        _log_settings_change(request.user, 'Clinic Information', 'Updated clinic profile')
        messages.success(request, 'Clinic information updated successfully.')
        return redirect('settings:admin_settings')
    else:
        messages.error(request, 'Please correct the errors below.')
        return _render_with_error(request, 'clinic', form)


def _handle_appointments_form(request):
    """Handle appointment settings form submission."""
    form = AppointmentSettingsForm(request.POST)
    if form.is_valid():
        data = form.cleaned_data
        set_setting('appointment_slot_duration', data['slot_duration'], request.user, 'APPOINTMENT')
        set_setting('appointment_max_advance_days', data['max_advance_days'], request.user, 'APPOINTMENT')
        set_setting('appointment_min_advance_hours', data['min_advance_hours'], request.user, 'APPOINTMENT')
        set_setting('appointment_allow_walk_ins', data['allow_walk_ins'], request.user, 'APPOINTMENT')
        set_setting('appointment_daily_limit', data['daily_limit'], request.user, 'APPOINTMENT')
        set_setting('appointment_require_confirmation', data['require_confirmation'], request.user, 'APPOINTMENT')
        set_setting('appointment_auto_cancel_hours', data['auto_cancel_hours'], request.user, 'APPOINTMENT')
        set_setting('appointment_reminder_hours', data['reminder_hours'], request.user, 'APPOINTMENT')

        messages.success(request, 'Appointment settings updated successfully.')
        return redirect('settings:admin_settings')
    else:
        messages.error(request, 'Please correct the errors below.')
        return _render_with_error(request, 'appointments', form)


def _handle_inventory_form(request):
    """Handle inventory settings form submission."""
    form = InventorySettingsForm(request.POST)
    if form.is_valid():
        data = form.cleaned_data
        set_setting('inventory_low_stock_threshold', data['low_stock_threshold'], request.user, 'INVENTORY')
        set_setting('inventory_critical_threshold', data['critical_threshold'], request.user, 'INVENTORY')
        set_setting('inventory_enable_alerts', data['enable_alerts'], request.user, 'INVENTORY')
        set_setting('inventory_allow_negative', data['allow_negative'], request.user, 'INVENTORY')
        set_setting('inventory_expiry_warning_days', data['expiry_warning_days'], request.user, 'INVENTORY')

        messages.success(request, 'Inventory settings updated successfully.')
        return redirect('settings:admin_settings')
    else:
        messages.error(request, 'Please correct the errors below.')
        return _render_with_error(request, 'inventory', form)


def _handle_notifications_form(request):
    """Handle notification settings form submission."""
    form = NotificationSettingsForm(request.POST)
    if form.is_valid():
        data = form.cleaned_data
        set_setting('notification_email_enabled', data['email_enabled'], request.user, 'NOTIFICATION')
        set_setting('notification_sms_enabled', data['sms_enabled'], request.user, 'NOTIFICATION')
        set_setting('notification_sms_provider', data['sms_provider'], request.user, 'NOTIFICATION')

        # Only update API key if provided (not empty)
        if data['sms_api_key']:
            set_setting('notification_sms_api_key', data['sms_api_key'], request.user, 'NOTIFICATION')
            # Mark as sensitive
            try:
                setting = SystemSetting.objects.get(key='notification_sms_api_key')
                setting.is_sensitive = True
                setting.save()
            except SystemSetting.DoesNotExist:
                pass

        set_setting('notification_from_email', data['from_email'], request.user, 'NOTIFICATION')
        set_setting('notification_sender_name', data['sender_name'], request.user, 'NOTIFICATION')

        messages.success(request, 'Notification settings updated successfully.')
        return redirect('settings:admin_settings')
    else:
        messages.error(request, 'Please correct the errors below.')
        return _render_with_error(request, 'notifications', form)


def _handle_payroll_form(request):
    """Handle payroll settings form submission."""
    form = PayrollSettingsForm(request.POST)
    if form.is_valid():
        data = form.cleaned_data
        set_setting('payroll_period_type', data['period_type'], request.user, 'PAYROLL')
        set_setting('payroll_work_hours_per_day', data['work_hours_per_day'], request.user, 'PAYROLL')
        set_setting('payroll_overtime_threshold', data['overtime_threshold'], request.user, 'PAYROLL')
        set_setting('payroll_enable_sss', data['enable_sss'], request.user, 'PAYROLL')
        set_setting('payroll_enable_philhealth', data['enable_philhealth'], request.user, 'PAYROLL')
        set_setting('payroll_enable_pagibig', data['enable_pagibig'], request.user, 'PAYROLL')
        set_setting('payroll_auto_statutory', data['auto_statutory'], request.user, 'PAYROLL')

        messages.success(request, 'Payroll settings updated successfully.')
        return redirect('settings:admin_settings')
    else:
        messages.error(request, 'Please correct the errors below.')
        return _render_with_error(request, 'payroll', form)


def _handle_system_form(request):
    """Handle system settings form submission."""
    form = SystemSettingsForm(request.POST)
    if form.is_valid():
        data = form.cleaned_data
        set_setting('system_date_format', data['date_format'], request.user, 'SYSTEM')
        set_setting('system_time_format', data['time_format'], request.user, 'SYSTEM')
        set_setting('system_maintenance_mode', data['maintenance_mode'], request.user, 'SYSTEM')
        set_setting('system_maintenance_message', data['maintenance_message'], request.user, 'SYSTEM')

        messages.success(request, 'System settings updated successfully.')
        return redirect('settings:admin_settings')
    else:
        messages.error(request, 'Please correct the errors below.')
        return _render_with_error(request, 'system', form)


def _handle_medical_form(request):
    """Handle medical records settings form submission."""
    form = MedicalRecordsSettingsForm(request.POST)
    if form.is_valid():
        data = form.cleaned_data
        set_setting('medical_default_followup_days', data['default_followup_days'], request.user, 'MEDICAL')
        set_setting('medical_require_diagnosis', data['require_diagnosis'], request.user, 'MEDICAL')
        set_setting('medical_vaccination_reminders', data['vaccination_reminders'], request.user, 'MEDICAL')
        set_setting('medical_reminder_days_before', data['reminder_days_before'], request.user, 'MEDICAL')

        messages.success(request, 'Medical records settings updated successfully.')
        return redirect('settings:admin_settings')
    else:
        messages.error(request, 'Please correct the errors below.')
        return _render_with_error(request, 'medical', form)


def _render_with_error(request, active_tab, error_form):
    """Re-render the settings page with an error form."""
    clinic_profile = ClinicProfile.get_instance()

    forms_dict = {
        'clinic': ClinicInfoForm(instance=clinic_profile),
        'scheduling': {
            'appointments': AppointmentSettingsForm(),
            'medical': MedicalRecordsSettingsForm(),
        },
        'inventory': InventorySettingsForm(),
        'notifications': NotificationSettingsForm(),
        'payroll': PayrollSettingsForm(),
        'system': SystemSettingsForm(),
        'content': _get_content_forms(),
    }

    # Handle scheduling tab error forms specially
    if active_tab in ['appointments', 'medical']:
        forms_dict['scheduling'][active_tab] = error_form
        active_tab = 'scheduling'
    else:
        # Replace with the error form
        forms_dict[active_tab] = error_form

    context = {
        'forms': forms_dict,
        'active_tab': active_tab,
        'tabs': SETTINGS_TABS,
        'clinic_profile': clinic_profile,
    }

    return render(request, 'settings/settings_main.html', context)


def _log_settings_change(user, category, details):
    """Log a settings change to the activity log."""
    ActivityLog.objects.create(
        user=user,
        action=f"Updated {category}",
        category=ActivityLog.Category.SYSTEM,
        branch=user.branch if hasattr(user, 'branch') else None,
        details=details
    )


# =============================================================================
# Content Management Functions
# =============================================================================

def _get_content_forms():
    """Get all content management forms and data."""
    return {
        'hero': HeroSectionForm(),
        'mission_vision': MissionVisionForm(),
        'services_intro': ServicesIntroForm(),
        'vets_intro': VetsIntroForm(),
        'hero_stats': HeroStat.objects.all(),
        'services': Service.objects.all(),
        'veterinarians': Veterinarian.objects.all(),
        'branches': Branch.objects.filter(is_active=True).order_by('display_order', 'name'),
        # Empty forms for adding new items
        'hero_stat_form': HeroStatForm(),
        'service_form': ServiceForm(),
        'veterinarian_form': VeterinarianForm(),
    }


def _handle_content_form(request):
    """Route content form submissions to appropriate handlers."""
    sub_form = request.POST.get('sub_form')

    if sub_form == 'hero':
        return _handle_hero_form(request)
    elif sub_form == 'mission_vision':
        return _handle_mission_vision_form(request)
    elif sub_form == 'services_intro':
        return _handle_services_intro_form(request)
    elif sub_form == 'vets_intro':
        return _handle_vets_intro_form(request)
    elif sub_form == 'hero_stat':
        return _handle_hero_stat_form(request)
    elif sub_form == 'core_value':
        return _handle_core_value_form(request)
    elif sub_form == 'service':
        return _handle_service_form(request)
    elif sub_form == 'veterinarian':
        return _handle_veterinarian_form(request)
    elif sub_form == 'delete_hero_stat':
        return _handle_delete_hero_stat(request)
    elif sub_form == 'delete_core_value':
        return _handle_delete_core_value(request)
    elif sub_form == 'delete_service':
        return _handle_delete_service(request)
    elif sub_form == 'delete_veterinarian':
        return _handle_delete_veterinarian(request)

    messages.error(request, 'Invalid form submission.')
    return redirect('settings:admin_settings')


def _handle_hero_form(request):
    """Save hero section content."""
    form = HeroSectionForm(request.POST)
    if form.is_valid():
        SectionContent.objects.update_or_create(
            section_type='HERO',
            defaults={
                'title': form.cleaned_data['title'],
                'subtitle': form.cleaned_data['subtitle'],
                'description': form.cleaned_data['description'],
            }
        )
        _log_settings_change(request.user, 'Hero Section', 'Updated hero content')
        messages.success(request, 'Hero section updated successfully.')
    else:
        messages.error(request, 'Please correct the errors.')
    return redirect('settings:admin_settings')


def _handle_mission_vision_form(request):
    """Save mission, vision, and core values content."""
    form = MissionVisionForm(request.POST)
    if form.is_valid():
        SectionContent.objects.update_or_create(
            section_type='MISSION',
            defaults={
                'title': form.cleaned_data['mission_title'],
                'description': form.cleaned_data['mission_description'],
            }
        )
        SectionContent.objects.update_or_create(
            section_type='VISION',
            defaults={
                'title': form.cleaned_data['vision_title'],
                'description': form.cleaned_data['vision_description'],
            }
        )
        SectionContent.objects.update_or_create(
            section_type='CORE_VALUES_INTRO',
            defaults={
                'title': form.cleaned_data['core_values_title'],
                'description': form.cleaned_data['core_values_description'],
            }
        )
        _log_settings_change(request.user, 'Mission, Vision & Core Values', 'Updated mission, vision, and core values content')
        messages.success(request, 'Mission, Vision & Core Values updated successfully.')
    else:
        messages.error(request, 'Please correct the errors.')
    return redirect('settings:admin_settings')


def _handle_services_intro_form(request):
    """Save services intro content."""
    form = ServicesIntroForm(request.POST)
    if form.is_valid():
        SectionContent.objects.update_or_create(
            section_type='SERVICES_INTRO',
            defaults={
                'title': form.cleaned_data['title'],
                'subtitle': form.cleaned_data['subtitle'],
            }
        )
        _log_settings_change(request.user, 'Services Intro', 'Updated services section intro')
        messages.success(request, 'Services intro updated successfully.')
    else:
        messages.error(request, 'Please correct the errors.')
    return redirect('settings:admin_settings')


def _handle_vets_intro_form(request):
    """Save veterinarians intro content."""
    form = VetsIntroForm(request.POST)
    if form.is_valid():
        SectionContent.objects.update_or_create(
            section_type='VETS_INTRO',
            defaults={
                'title': form.cleaned_data['title'],
                'subtitle': form.cleaned_data['subtitle'],
            }
        )
        _log_settings_change(request.user, 'Veterinarians Intro', 'Updated veterinarians section intro')
        messages.success(request, 'Veterinarians intro updated successfully.')
    else:
        messages.error(request, 'Please correct the errors.')
    return redirect('settings:admin_settings')


def _handle_hero_stat_form(request):
    """Add or update a hero statistic."""
    stat_id = request.POST.get('item_id')
    if stat_id:
        instance = get_object_or_404(HeroStat, pk=stat_id)
        form = HeroStatForm(request.POST, instance=instance)
        action = 'Updated'
    else:
        form = HeroStatForm(request.POST)
        action = 'Added'

    if form.is_valid():
        form.save()
        _log_settings_change(request.user, 'Hero Statistics', f'{action} hero stat')
        messages.success(request, f'Hero statistic {action.lower()} successfully.')
    else:
        messages.error(request, 'Please correct the errors.')
    return redirect('settings:admin_settings')


def _handle_core_value_form(request):
    """Add or update a core value."""
    value_id = request.POST.get('item_id')
    if value_id:
        instance = get_object_or_404(CoreValue, pk=value_id)
        form = CoreValueForm(request.POST, instance=instance)
        action = 'Updated'
    else:
        form = CoreValueForm(request.POST)
        action = 'Added'

    if form.is_valid():
        form.save()
        _log_settings_change(request.user, 'Core Values', f'{action} core value')
        messages.success(request, f'Core value {action.lower()} successfully.')
    else:
        messages.error(request, 'Please correct the errors.')
    return redirect('settings:admin_settings')


def _handle_service_form(request):
    """Add or update a service."""
    service_id = request.POST.get('item_id')
    if service_id:
        instance = get_object_or_404(Service, pk=service_id)
        form = ServiceForm(request.POST, request.FILES, instance=instance)
        action = 'Updated'
    else:
        form = ServiceForm(request.POST, request.FILES)
        action = 'Added'

    if form.is_valid():
        form.save()
        _log_settings_change(request.user, 'Services', f'{action} service')
        messages.success(request, f'Service {action.lower()} successfully.')
    else:
        messages.error(request, 'Please correct the errors.')
    return redirect('settings:admin_settings')


def _handle_veterinarian_form(request):
    """Add or update a veterinarian."""
    vet_id = request.POST.get('item_id')
    if vet_id:
        instance = get_object_or_404(Veterinarian, pk=vet_id)
        form = VeterinarianForm(request.POST, request.FILES, instance=instance)
        action = 'Updated'
    else:
        form = VeterinarianForm(request.POST, request.FILES)
        action = 'Added'

    if form.is_valid():
        form.save()
        _log_settings_change(request.user, 'Veterinarians', f'{action} veterinarian')
        messages.success(request, f'Veterinarian {action.lower()} successfully.')
    else:
        messages.error(request, 'Please correct the errors.')
    return redirect('settings:admin_settings')


def _handle_delete_hero_stat(request):
    """Delete a hero statistic."""
    stat_id = request.POST.get('item_id')
    if stat_id:
        HeroStat.objects.filter(pk=stat_id).delete()
        _log_settings_change(request.user, 'Hero Statistics', 'Deleted hero stat')
        messages.success(request, 'Hero statistic deleted.')
    return redirect('settings:admin_settings')


def _handle_delete_core_value(request):
    """Delete a core value."""
    value_id = request.POST.get('item_id')
    if value_id:
        CoreValue.objects.filter(pk=value_id).delete()
        _log_settings_change(request.user, 'Core Values', 'Deleted core value')
        messages.success(request, 'Core value deleted.')
    return redirect('settings:admin_settings')


def _handle_delete_service(request):
    """Delete a service."""
    service_id = request.POST.get('item_id')
    if service_id:
        Service.objects.filter(pk=service_id).delete()
        _log_settings_change(request.user, 'Services', 'Deleted service')
        messages.success(request, 'Service deleted.')
    return redirect('settings:admin_settings')


def _handle_delete_veterinarian(request):
    """Delete a veterinarian."""
    vet_id = request.POST.get('item_id')
    if vet_id:
        Veterinarian.objects.filter(pk=vet_id).delete()
        _log_settings_change(request.user, 'Veterinarians', 'Deleted veterinarian')
        messages.success(request, 'Veterinarian deleted.')
    return redirect('settings:admin_settings')


# =============================================================================
# Configurable Options CRUD Handlers
# =============================================================================

def _handle_reason_for_visit_form(request):
    """Add or update a reason for visit."""
    item_id = request.POST.get('item_id')
    if item_id:
        instance = get_object_or_404(ReasonForVisit, pk=item_id)
        form = ReasonForVisitForm(request.POST, instance=instance)
        action = 'Updated'
    else:
        form = ReasonForVisitForm(request.POST)
        action = 'Added'

    if form.is_valid():
        form.save()
        _log_settings_change(request.user, 'Reasons for Visit', f'{action} reason for visit')
        messages.success(request, f'Reason for visit {action.lower()} successfully.')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f'{field}: {error}')
    return redirect('settings:scheduling_settings')


def _handle_clinical_status_form(request):
    """Add or update a clinical status."""
    item_id = request.POST.get('item_id')
    if item_id:
        instance = get_object_or_404(ClinicalStatus, pk=item_id)
        form = ClinicalStatusForm(request.POST, instance=instance)
        action = 'Updated'
    else:
        form = ClinicalStatusForm(request.POST)
        action = 'Added'

    if form.is_valid():
        form.save()
        _log_settings_change(request.user, 'Clinical Statuses', f'{action} clinical status')
        messages.success(request, f'Clinical status {action.lower()} successfully.')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f'{field}: {error}')
    return redirect('settings:scheduling_settings')


def _handle_delete_reason(request):
    """Delete a reason for visit."""
    item_id = request.POST.get('item_id')
    if item_id:
        reason = ReasonForVisit.objects.filter(pk=item_id).first()
        if reason:
            # Check if this reason is being used by any appointments
            from appointments.models import Appointment
            usage_count = Appointment.objects.filter(reason_for_visit=reason).count()
            if usage_count > 0:
                messages.error(
                    request,
                    f'Cannot delete "{reason.name}" - it is used by {usage_count} appointment(s). '
                    'Consider deactivating it instead.'
                )
            else:
                reason.delete()
                _log_settings_change(request.user, 'Reasons for Visit', 'Deleted reason for visit')
                messages.success(request, 'Reason for visit deleted.')
    return redirect('settings:scheduling_settings')


def _handle_delete_status(request):
    """Delete a clinical status."""
    item_id = request.POST.get('item_id')
    if item_id:
        status = ClinicalStatus.objects.filter(pk=item_id).first()
        if status:
            # Check if this status is being used by any pets
            from patients.models import Pet
            usage_count = Pet.objects.filter(clinical_status=status).count()
            if usage_count > 0:
                messages.error(
                    request,
                    f'Cannot delete "{status.name}" - it is used by {usage_count} patient(s). '
                    'Consider deactivating it instead.'
                )
            else:
                status.delete()
                _log_settings_change(request.user, 'Clinical Statuses', 'Deleted clinical status')
                messages.success(request, 'Clinical status deleted.')
    return redirect('settings:scheduling_settings')


@login_required
@admin_only
@module_permission_required('settings', 'MANAGE')
def reason_for_visit_detail(request, pk):
    """Get details of a reason for visit for editing."""
    reason = get_object_or_404(ReasonForVisit, pk=pk)
    return JsonResponse({
        'id': reason.pk,
        'name': reason.name,
        'code': reason.code,
        'description': reason.description,
        'order': reason.order,
        'is_active': reason.is_active,
    })


@login_required
@admin_only
@module_permission_required('settings', 'MANAGE')
def clinical_status_detail(request, pk):
    """Get details of a clinical status for editing."""
    status = get_object_or_404(ClinicalStatus, pk=pk)
    return JsonResponse({
        'id': status.pk,
        'name': status.name,
        'code': status.code,
        'description': status.description,
        'color': status.color,
        'order': status.order,
        'is_active': status.is_active,
    })


@admin_only
def reorder_reasons(request):
    """Update the order of reasons for visit."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'})
    
    try:
        import json
        data = json.loads(request.body)
        items = data.get('items', [])
        
        for item in items:
            ReasonForVisit.objects.filter(pk=item['id']).update(order=item['order'])
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@admin_only
def reorder_statuses(request):
    """Update the order of clinical statuses."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'})
    
    try:
        import json
        data = json.loads(request.body)
        items = data.get('items', [])
        
        for item in items:
            ClinicalStatus.objects.filter(pk=item['id']).update(order=item['order'])
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
