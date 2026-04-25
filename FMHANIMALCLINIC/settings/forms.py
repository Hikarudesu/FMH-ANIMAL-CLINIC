"""Forms for settings."""
# pylint: disable=no-member, line-too-long, trailing-whitespace, missing-docstring, import-outside-toplevel

from django import forms
from django.db import models

from FMHANIMALCLINIC.form_mixins import AdminInputMixin, validate_philippines_phone
from notifications.delivery import normalize_ph_sim_number
from .models import (
    ClinicProfile, SectionContent, HeroStat,
    CoreValue, Service, Veterinarian,
)
from .utils import get_setting


class ClinicInfoForm(AdminInputMixin, forms.ModelForm):
    """Form for clinic profile/branding settings."""

    tos_content = forms.CharField(
        label="Terms of Service",
        widget=forms.Textarea(attrs={'rows': 10, 'placeholder': 'Enter the Terms of Service content here...'}),
        required=False,
        help_text="Full text of your clinic's Terms of Service."
    )
    privacy_policy_content = forms.CharField(
        label="Privacy Policy",
        widget=forms.Textarea(attrs={'rows': 10, 'placeholder': 'Enter the Privacy Policy content here...'}),
        required=False,
        help_text="Full text of your clinic's Privacy Policy."
    )
    class Meta:
        model = ClinicProfile
        fields = [
            'name', 'logo',
            'clinic_title', 'clinic_slogan', 'hero_description',
            'email', 'phone', 'address', 'license_number',
            'facebook_url', 'instagram_url', 'messenger_url', 'tiktok_url',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Enter clinic name'}),
            'clinic_title': forms.TextInput(attrs={'placeholder': 'Enter landing page title'}),
            'clinic_slogan': forms.TextInput(attrs={'placeholder': 'Enter short slogan'}),
            'hero_description': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Enter landing page description'}),
            'email': forms.EmailInput(attrs={'placeholder': 'contact@example.com'}),
            'phone': forms.TextInput(attrs={
                'placeholder': '09XXXXXXXXX',
                'inputmode': 'numeric',
                'pattern': '[0-9]{11}',
                'minlength': '11',
                'maxlength': '11',
                'oninput': "this.value=this.value.replace(/\\D/g,'')",
            }),
            'address': forms.Textarea(attrs={
                'rows': 3, 'placeholder': 'Enter full address'
            }),
            'license_number': forms.TextInput(attrs={'placeholder': 'Business/Vet license number'}),
            'facebook_url': forms.URLInput(attrs={'placeholder': 'https://facebook.com/your-page'}),
            'instagram_url': forms.URLInput(attrs={'placeholder': 'https://instagram.com/your-page'}),
            'messenger_url': forms.URLInput(attrs={'placeholder': 'https://m.me/your-page'}),
            'tiktok_url': forms.URLInput(attrs={'placeholder': 'https://www.tiktok.com/@your-page'}),
            'logo': forms.FileInput(attrs={'accept': 'image/*'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import LegalDocument
        
        # Load active TOS and Privacy Policy
        tos = LegalDocument.objects.filter(
            document_type=LegalDocument.DocumentType.TERMS_OF_SERVICE
        ).first()
        if tos:
            self.fields['tos_content'].initial = tos.content
            
        privacy = LegalDocument.objects.filter(
            document_type=LegalDocument.DocumentType.PRIVACY_POLICY
        ).first()
        if privacy:
            self.fields['privacy_policy_content'].initial = privacy.content

    def clean_phone(self):
        return validate_philippines_phone(self.cleaned_data.get('phone', ''))

    def save(self, commit=True):
        instance = super().save(commit=commit)
        if commit:
            from .models import LegalDocument
            
            # Save or update TOS
            tos_content = self.cleaned_data.get('tos_content')
            if tos_content is not None:
                tos = LegalDocument.objects.filter(
                    document_type=LegalDocument.DocumentType.TERMS_OF_SERVICE
                ).first()
                if tos:
                    if tos.content != tos_content:
                        tos.content = tos_content
                        parts = tos.version.split('.')
                        try:
                            tos.version = f"{parts[0]}.{int(parts[1]) + 1}" if len(parts) == 2 else f"{float(tos.version) + 0.1:.1f}"
                        except ValueError:
                            tos.version = "1.1"
                        tos.save()
                elif tos_content.strip():
                    LegalDocument.objects.create(
                        document_type=LegalDocument.DocumentType.TERMS_OF_SERVICE,
                        title="Terms of Service",
                        content=tos_content,
                        version="1.0",
                        is_active=True
                    )

            # Save or update Privacy Policy
            privacy_content = self.cleaned_data.get('privacy_policy_content')
            if privacy_content is not None:
                privacy = LegalDocument.objects.filter(
                    document_type=LegalDocument.DocumentType.PRIVACY_POLICY
                ).first()
                if privacy:
                    if privacy.content != privacy_content:
                        privacy.content = privacy_content
                        parts = privacy.version.split('.')
                        try:
                            privacy.version = f"{parts[0]}.{int(parts[1]) + 1}" if len(parts) == 2 else f"{float(privacy.version) + 0.1:.1f}"
                        except ValueError:
                            privacy.version = "1.1"
                        privacy.save()
                elif privacy_content.strip():
                    LegalDocument.objects.create(
                        document_type=LegalDocument.DocumentType.PRIVACY_POLICY,
                        title="Privacy Policy",
                        content=privacy_content,
                        version="1.0",
                        is_active=True
                    )
        return instance


class InventorySettingsForm(AdminInputMixin, forms.Form):
    """Form for inventory-related settings."""

    low_stock_threshold = forms.IntegerField(
        label='Low Stock Warning Threshold',
        min_value=1,
        widget=forms.NumberInput(),
        help_text='Warn when stock falls below this level'
    )
    critical_threshold = forms.IntegerField(
        label='Critical Stock Alert Threshold',
        min_value=0,
        widget=forms.NumberInput(),
        help_text='Critical alert when stock falls below this level'
    )
    enable_alerts = forms.BooleanField(
        label='Enable Stock Alerts',
        required=False,
        widget=forms.CheckboxInput(),
        help_text='Send notifications for low/critical stock'
    )
    allow_negative = forms.BooleanField(
        label='Allow Negative Stock',
        required=False,
        widget=forms.CheckboxInput(),
        help_text='Allow selling items when stock is zero'
    )
    expiry_warning_days = forms.IntegerField(
        label='Expiry Warning (days)',
        min_value=1,
        max_value=365,
        widget=forms.NumberInput(),
        help_text='Warn this many days before product expiry'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['low_stock_threshold'].initial = get_setting('inventory_low_stock_threshold', 10)
        self.fields['critical_threshold'].initial = get_setting('inventory_critical_threshold', 5)
        self.fields['enable_alerts'].initial = get_setting('inventory_enable_alerts', True)
        self.fields['allow_negative'].initial = get_setting('inventory_allow_negative', False)
        self.fields['expiry_warning_days'].initial = get_setting('inventory_expiry_warning_days', 30)


class NotificationSettingsForm(AdminInputMixin, forms.Form):
    """Form for notification-related settings."""

    email_enabled = forms.BooleanField(
        label='Enable Email Notifications',
        required=False,
        widget=forms.CheckboxInput(),
        help_text='Send notifications via email'
    )
    sms_enabled = forms.BooleanField(
        label='Enable SMS Notifications',
        required=False,
        widget=forms.CheckboxInput(),
        help_text='Send notifications via SMS'
    )
    sms_default_recipient = forms.CharField(
        label='Default SMS SIM Number (PH)',
        required=False,
        widget=forms.TextInput(attrs={'placeholder': '09XXXXXXXXX'}),
        help_text='Philippines mobile number only. Example: 09171234567'
    )
    from_email = forms.EmailField(
        label='From Email Address',
        widget=forms.EmailInput(attrs={'placeholder': 'noreply@example.com'}),
        help_text='Sender email address for notifications'
    )
    sender_name = forms.CharField(
        label='Sender Display Name',
        max_length=100,
        widget=forms.TextInput(attrs={'placeholder': 'FMH Animal Clinic'}),
        help_text='Display name for email sender'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email_enabled'].initial = get_setting('notification_email_enabled', True)
        self.fields['sms_enabled'].initial = get_setting('notification_sms_enabled', False)
        self.fields['sms_default_recipient'].initial = get_setting('notification_sms_default_recipient', '')
        self.fields['from_email'].initial = get_setting('notification_from_email', 'noreply@fmhclinic.com')
        self.fields['sender_name'].initial = get_setting('notification_sender_name', 'FMH Animal Clinic')

    def clean_sms_default_recipient(self):
        sim_number = (self.cleaned_data.get('sms_default_recipient') or '').strip()
        if not sim_number:
            return ''

        normalized = normalize_ph_sim_number(sim_number)
        if not normalized:
            raise forms.ValidationError('Enter a valid PH mobile number (e.g., 09171234567).')

        return normalized


class PayrollSettingsForm(AdminInputMixin, forms.Form):
    """Form for payroll-related settings."""

    # ─── Payroll Defaults ───
    default_work_days = forms.IntegerField(
        label='Default Working Days Per Month',
        min_value=1,
        max_value=31,
        widget=forms.NumberInput(),
        help_text='Default number of working days used when generating payslips (e.g. 22)'
    )
    default_staff_allowance = forms.DecimalField(
        label='Default Staff Allowance (₱)',
        min_value=0,
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'step': '100'}),
        help_text='Default monthly staff allowance applied to new payslips (split 50/50 on 15th & 30th)'
    )

    # ─── Employer Statutory Contributions ───
    auto_statutory = forms.BooleanField(
        label='Enable Employer Statutory Contributions',
        required=False,
        widget=forms.CheckboxInput(),
        help_text='Master toggle. When enabled, clinic-paid statutory contributions (SSS, PhilHealth, Pag-IBIG) are auto-calculated during payslip generation and shown on payslips. These are NOT deducted from employee salary.'
    )
    enable_sss = forms.BooleanField(
        label='SSS Contribution',
        required=False,
        widget=forms.CheckboxInput(),
        help_text='Calculate SSS employer contribution when generating payslips'
    )
    sss_rate = forms.DecimalField(
        label='SSS Employer Rate (%)',
        min_value=0,
        max_value=100,
        max_digits=5,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'step': '0.01'}),
        help_text='Percentage of base salary for SSS employer share (e.g. 4.50 = 4.5%)'
    )
    enable_philhealth = forms.BooleanField(
        label='PhilHealth Contribution',
        required=False,
        widget=forms.CheckboxInput(),
        help_text='Calculate PhilHealth employer contribution when generating payslips'
    )
    philhealth_rate = forms.DecimalField(
        label='PhilHealth Employer Rate (%)',
        min_value=0,
        max_value=100,
        max_digits=5,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'step': '0.01'}),
        help_text='Percentage of base salary for PhilHealth employer share (e.g. 2.00 = 2%)'
    )
    enable_pagibig = forms.BooleanField(
        label='Pag-IBIG Contribution',
        required=False,
        widget=forms.CheckboxInput(),
        help_text='Calculate Pag-IBIG employer contribution when generating payslips'
    )
    pagibig_fixed = forms.DecimalField(
        label='Pag-IBIG Fixed Amount (₱)',
        min_value=0,
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'step': '10'}),
        help_text='Fixed monthly Pag-IBIG employer contribution (e.g. ₱100)'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['default_work_days'].initial = get_setting('payroll_default_work_days', 22)
        self.fields['default_staff_allowance'].initial = get_setting('payroll_default_staff_allowance', 2000)
        self.fields['auto_statutory'].initial = get_setting('payroll_auto_statutory', True)
        self.fields['enable_sss'].initial = get_setting('payroll_enable_sss', True)
        self.fields['sss_rate'].initial = get_setting('payroll_sss_rate', 4.50)
        self.fields['enable_philhealth'].initial = get_setting('payroll_enable_philhealth', True)
        self.fields['philhealth_rate'].initial = get_setting('payroll_philhealth_rate', 2.00)
        self.fields['enable_pagibig'].initial = get_setting('payroll_enable_pagibig', True)
        self.fields['pagibig_fixed'].initial = get_setting('payroll_pagibig_fixed', 100)


class SystemSettingsForm(AdminInputMixin, forms.Form):
    """Form for system-wide settings."""

    # Date & Time Settings
    date_format = forms.ChoiceField(
        label='Date Format',
        choices=[
            ('M d, Y', 'Jan 15, 2025'),
            ('d/m/Y', '15/01/2025'),
            ('m/d/Y', '01/15/2025'),
            ('Y-m-d', '2025-01-15'),
        ],
        widget=forms.Select(),
        help_text='Format for displaying dates'
    )
    time_format = forms.ChoiceField(
        label='Time Format',
        choices=[
            ('h:i A', '12-hour (2:30 PM)'),
            ('H:i', '24-hour (14:30)'),
        ],
        widget=forms.Select(),
        help_text='Format for displaying times'
    )

    # Maintenance Settings
    maintenance_mode = forms.BooleanField(
        label='Maintenance Mode',
        required=False,
        widget=forms.CheckboxInput(),
        help_text='Enable maintenance mode (restricts access to admins only)'
    )
    maintenance_message = forms.CharField(
        label='Maintenance Message',
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'placeholder': 'System is under maintenance. Please check back later.'
        }),
        help_text='Message to display during maintenance'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date_format'].initial = get_setting('system_date_format', 'M d, Y')
        self.fields['time_format'].initial = get_setting('system_time_format', 'h:i A')
        self.fields['maintenance_mode'].initial = get_setting('system_maintenance_mode', False)
        self.fields['maintenance_message'].initial = get_setting('system_maintenance_message', '')


class AppointmentSettingsForm(AdminInputMixin, forms.Form):
    """Form for appointment scheduling settings."""

    max_advance_days = forms.IntegerField(
        label='Maximum Booking Window (days)',
        min_value=1,
        max_value=365,
        widget=forms.NumberInput(),
        help_text='Maximum days in the future users can book (e.g., 180 = 6 months)'
    )
    reminder_hours_1 = forms.IntegerField(
        label='First Reminder (hours before appointment)',
        min_value=1,
        max_value=72,
        widget=forms.NumberInput(),
        help_text='Send first reminder this many hours before (e.g., 24 = 1 day)'
    )
    reminder_hours_2 = forms.IntegerField(
        label='Second Reminder (hours before appointment)',
        min_value=1,
        max_value=72,
        widget=forms.NumberInput(),
        help_text='Send second reminder this many hours before (e.g., 3 = 3 hours)'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['max_advance_days'].initial = get_setting('appointment_max_advance_days', 180)
        self.fields['reminder_hours_1'].initial = get_setting('appointment_reminder_hours_1', 24)
        self.fields['reminder_hours_2'].initial = get_setting('appointment_reminder_hours_2', 3)


class MedicalRecordsSettingsForm(AdminInputMixin, forms.Form):
    """Form for medical records settings."""

    default_followup_days = forms.IntegerField(
        label='Default Follow-up Period (days)',
        min_value=1,
        max_value=90,
        widget=forms.NumberInput(),
        help_text='Default days until follow-up appointment'
    )
    vaccination_reminders = forms.BooleanField(
        label='Enable Vaccination Reminders',
        required=False,
        widget=forms.CheckboxInput(),
        help_text='Send reminders when vaccinations are due'
    )
    reminder_days_before = forms.IntegerField(
        label='Vaccination Reminder Notice (days)',
        min_value=1,
        max_value=30,
        widget=forms.NumberInput(),
        help_text='Days before vaccination due date to send reminder'
    )
    clinical_status_auto_actions = forms.BooleanField(
        label='Enable Clinical Status Auto-Actions',
        required=False,
        widget=forms.CheckboxInput(),
        help_text='Automatically run status-based owner notifications when clinical action changes'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['default_followup_days'].initial = get_setting('medical_default_followup_days', 7)
        self.fields['vaccination_reminders'].initial = get_setting('medical_vaccination_reminders', True)
        self.fields['reminder_days_before'].initial = get_setting('medical_reminder_days_before', 7)
        self.fields['clinical_status_auto_actions'].initial = get_setting('medical_clinical_status_auto_actions', True)


# =============================================================================
# Content Management Forms
# =============================================================================

class HeroSectionForm(AdminInputMixin, forms.Form):
    """Form for hero section content."""

    title = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={'placeholder': 'FMH ANIMAL CLINIC'}),
        help_text='Main hero title'
    )
    subtitle = forms.CharField(
        max_length=500,
        widget=forms.TextInput(attrs={'placeholder': 'Powered by AI Diagnostics'}),
        help_text='Hero subtitle'
    )
    description = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'A centralized multi-branch veterinary system...'
        }),
        help_text='Hero description paragraph'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            content = SectionContent.objects.get(section_type='HERO')
            self.fields['title'].initial = content.title
            self.fields['subtitle'].initial = content.subtitle
            self.fields['description'].initial = content.description
        except SectionContent.DoesNotExist:
            pass


class MissionVisionForm(AdminInputMixin, forms.Form):
    """Form for mission, vision, and core values content."""

    mission_title = forms.CharField(
        max_length=255,
        widget=forms.TextInput(),
        help_text='Mission section title'
    )
    mission_description = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
        help_text='Mission statement text'
    )
    vision_title = forms.CharField(
        max_length=255,
        widget=forms.TextInput(),
        help_text='Vision section title'
    )
    vision_description = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
        help_text='Vision statement text'
    )
    core_values_title = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(),
        help_text='Core Values section title'
    )
    core_values_description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 4}),
        help_text='Core Values intro paragraph'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Load existing data
        try:
            mission = SectionContent.objects.get(section_type='MISSION')
            self.fields['mission_title'].initial = mission.title
            self.fields['mission_description'].initial = mission.description
        except SectionContent.DoesNotExist:
            pass

        try:
            vision = SectionContent.objects.get(section_type='VISION')
            self.fields['vision_title'].initial = vision.title
            self.fields['vision_description'].initial = vision.description
        except SectionContent.DoesNotExist:
            pass

        try:
            core_values = SectionContent.objects.get(section_type='CORE_VALUES_INTRO')
            self.fields['core_values_title'].initial = core_values.title
            self.fields['core_values_description'].initial = core_values.description
        except SectionContent.DoesNotExist:
            pass


class ServicesIntroForm(AdminInputMixin, forms.Form):
    """Form for services section intro."""

    title = forms.CharField(
        max_length=255,
        widget=forms.TextInput(),
        help_text='Services section title'
    )
    subtitle = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.TextInput(),
        help_text='Services section subtitle'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            content = SectionContent.objects.get(section_type='SERVICES_INTRO')
            self.fields['title'].initial = content.title
            self.fields['subtitle'].initial = content.subtitle
        except SectionContent.DoesNotExist:
            pass


class VetsIntroForm(AdminInputMixin, forms.Form):
    """Form for veterinarians section intro."""

    title = forms.CharField(
        max_length=255,
        widget=forms.TextInput(),
        help_text='Veterinarians section title'
    )
    subtitle = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.TextInput(),
        help_text='Veterinarians section subtitle'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            content = SectionContent.objects.get(section_type='VETS_INTRO')
            self.fields['title'].initial = content.title
            self.fields['subtitle'].initial = content.subtitle
        except SectionContent.DoesNotExist:
            pass


class HeroStatForm(AdminInputMixin, forms.ModelForm):
    """Form for individual hero statistic."""

    class Meta:
        model = HeroStat
        fields = ['value', 'label', 'order', 'is_active']
        widgets = {
            'value': forms.TextInput(attrs={'placeholder': "e.g., '3', 'AI', '24/7'"}),
            'label': forms.TextInput(attrs={'placeholder': 'e.g., Clinic Branches'}),
            'order': forms.NumberInput(attrs={'style': 'width: 80px;'}),
            'is_active': forms.CheckboxInput(),
        }


class CoreValueForm(AdminInputMixin, forms.ModelForm):
    """Form for individual core value."""

    class Meta:
        model = CoreValue
        fields = ['title', 'icon', 'description', 'order', 'is_active']
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'Value name'}),
            'icon': forms.TextInput(attrs={'placeholder': 'bx-heart'}),
            'description': forms.Textarea(attrs={
                'rows': 2, 'placeholder': 'Optional description'
            }),
            'order': forms.NumberInput(attrs={'style': 'width: 80px;'}),
            'is_active': forms.CheckboxInput(),
        }


class ServiceForm(AdminInputMixin, forms.ModelForm):
    """Form for individual service."""

    class Meta:
        model = Service
        fields = ['title', 'description', 'icon', 'image', 'order', 'is_active']
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'Service name'}),
            'description': forms.Textarea(attrs={
                'rows': 3, 'placeholder': 'Service description'
            }),
            'icon': forms.TextInput(attrs={'placeholder': 'bx-plus-medical'}),
            'image': forms.FileInput(attrs={'accept': 'image/*'}),
            'order': forms.NumberInput(attrs={'style': 'width: 80px;'}),
            'is_active': forms.CheckboxInput(),
        }


class VeterinarianForm(AdminInputMixin, forms.ModelForm):
    """Form for individual veterinarian."""

    class Meta:
        model = Veterinarian
        fields = ['name', 'title', 'bio', 'photo', 'order', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Full name (without Dr.)'}),
            'title': forms.TextInput(attrs={'placeholder': 'e.g., Senior Veterinarian'}),
            'bio': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Short biography'}),
            'photo': forms.FileInput(attrs={'accept': 'image/*'}),
            'order': forms.NumberInput(attrs={'style': 'width: 80px;'}),
            'is_active': forms.CheckboxInput(),
        }


# =============================================================================
# Configurable Options Forms
# =============================================================================

class ReasonForVisitForm(AdminInputMixin, forms.ModelForm):
    """Form for managing reason for visit options."""

    class Meta:
        from .models import ReasonForVisit
        model = ReasonForVisit
        fields = ['name']  # Only name field needed
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'e.g., General Consultation',
                'class': 'admin-input',
            }),
        }
    
    def save(self, commit=True):
        """Override save to auto-generate code and set defaults."""
        instance = super().save(commit=False)
        
        # Auto-generate code from name if not provided
        if not instance.code:
            # Convert name to uppercase code (remove special chars, replace spaces with underscores)
            import re
            code = re.sub(r'[^A-Za-z0-9\s]', '', instance.name)  # Remove special chars
            code = re.sub(r'\s+', '_', code.strip())  # Replace spaces with underscores
            base_code = code.upper() or 'REASON'

            # Ensure generated code remains unique and avoid IntegrityError on save.
            unique_code = base_code
            suffix = 2
            from .models import ReasonForVisit
            while ReasonForVisit.objects.filter(code=unique_code).exclude(pk=instance.pk).exists():
                unique_code = f"{base_code}_{suffix}"
                suffix += 1

            instance.code = unique_code
        
        # Set defaults
        if instance.order is None:
            # Get next order number
            from .models import ReasonForVisit
            max_order = ReasonForVisit.objects.aggregate(max_order=models.Max('order'))['max_order'] or 0
            instance.order = max_order + 1
        
        if instance.is_active is None:
            instance.is_active = True
        
        if commit:
            instance.save()
        return instance


class ClinicalStatusForm(AdminInputMixin, forms.ModelForm):
    """Form for managing clinical status options."""

    class Meta:
        from .models import ClinicalStatus
        model = ClinicalStatus
        fields = ['name']  # Only name field needed
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'e.g., Healthy',
                'class': 'admin-input',
            }),
        }
    
    def save(self, commit=True):
        """Override save to auto-generate code and set defaults."""
        instance = super().save(commit=False)
        
        # Auto-generate code from name if not provided
        if not instance.code:
            # Convert name to uppercase code (remove special chars, replace spaces with underscores)
            import re
            code = re.sub(r'[^A-Za-z0-9\s]', '', instance.name)  # Remove special chars
            code = re.sub(r'\s+', '_', code.strip())  # Replace spaces with underscores
            base_code = code.upper() or 'STATUS'

            # Ensure generated code remains unique and avoid IntegrityError on save.
            unique_code = base_code
            suffix = 2
            from .models import ClinicalStatus
            while ClinicalStatus.objects.filter(code=unique_code).exclude(pk=instance.pk).exists():
                unique_code = f"{base_code}_{suffix}"
                suffix += 1

            instance.code = unique_code
        
        # Set defaults
        if instance.order is None:
            # Get next order number
            from .models import ClinicalStatus
            max_order = ClinicalStatus.objects.aggregate(max_order=models.Max('order'))['max_order'] or 0
            instance.order = max_order + 1
        
        if instance.is_active is None:
            instance.is_active = True
        
        if not instance.color:
            # Assign a default color based on name or use a standard one
            default_colors = {
                'healthy': '#4caf50',
                'critical': '#f44336', 
                'surgery': '#9c27b0',
                'treatment': '#2196f3',
                'monitoring': '#ff9800',
                'diagnostics': '#607d8b',
            }
            name_lower = instance.name.lower()
            instance.color = next((color for keyword, color in default_colors.items() if keyword in name_lower), '#757575')
        
        if commit:
            instance.save()
        return instance


