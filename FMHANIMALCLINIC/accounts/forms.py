"""
Forms for the accounts application.
"""
from django import forms
from django.contrib.auth.forms import UserCreationForm
from FMHANIMALCLINIC.form_mixins import FormControlMixin, validate_philippines_phone
from .models import User
from .rbac_models import Role
from branches.models import Branch


class PetOwnerRegistrationForm(FormControlMixin, UserCreationForm):
    """Registration form specifically for Pet Owners"""

    first_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'First name'})
    )

    last_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'Last name'})
    )

    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'placeholder': 'Enter your email'})
    )

    phone_number = forms.CharField(
        max_length=11,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': '09XXXXXXXXX',
            'inputmode': 'numeric',
            'pattern': '[0-9]{11}',
            'minlength': '11',
            'maxlength': '11',
            'oninput': "this.value=this.value.replace(/\\D/g,'')",
        })
    )

    address = forms.CharField(
        widget=forms.Textarea(attrs={
            'placeholder': 'Enter your complete address',
            'rows': 3,
        }),
        required=True,
        help_text=(
            'Please provide your complete address including '
            'street, barangay, city, and province'
        )
    )

    terms = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(),
        label='I agree to the Terms of Service and Privacy Policy'
    )

    class Meta:
        """Meta options for PetOwnerRegistrationForm."""
        model = User
        fields = ('username', 'first_name', 'last_name', 'email',
                  'phone_number', 'address', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Customize username field
        self.fields['username'].widget.attrs.update({
            'placeholder': 'Create a username',
        })

        # Customize password fields
        self.fields['password1'].widget.attrs.update({
            'placeholder': 'Create a password',
        })

        self.fields['password2'].widget.attrs.update({
            'placeholder': 'Confirm your password',
        })

    def clean_username(self):
        """Ensure the username is unique."""
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("This username is already in use. Please choose another.")
        return username

    def clean_phone_number(self):
        return validate_philippines_phone(self.cleaned_data.get('phone_number', ''))

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.phone_number = self.cleaned_data['phone_number']
        user.address = self.cleaned_data['address']

        if commit:
            user.save()
        return user

    def clean_email(self):
        """Ensure the email is unique."""
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(
                "A user with this email already exists.")
        return email


class UserProfileUpdateForm(FormControlMixin, forms.ModelForm):
    """Form for updating user profile details."""

    class Meta:
        """Meta options for UserProfileUpdateForm."""
        model = User
        fields = ('first_name', 'last_name',
                  'email', 'phone_number', 'address', 'branch', 'profile_picture')
        widgets = {
            'first_name': forms.TextInput(attrs={'placeholder': ' '}),
            'last_name': forms.TextInput(attrs={'placeholder': ' '}),
            'email': forms.EmailInput(attrs={'placeholder': ' '}),
            'phone_number': forms.TextInput(attrs={
                'placeholder': ' ',
                'inputmode': 'numeric',
                'pattern': '[0-9]{11}',
                'minlength': '11',
                'maxlength': '11',
                'oninput': "this.value=this.value.replace(/\\D/g,'')",
            }),
            'address': forms.TextInput(attrs={'placeholder': ' '}),
            'branch': forms.Select(),
            'profile_picture': forms.FileInput(),
        }

    def clean_phone_number(self):
        return validate_philippines_phone(self.cleaned_data.get('phone_number', ''))


class AdminAccountCreationForm(FormControlMixin, UserCreationForm):
    """Form for admins to create new accounts with role assignment."""

    first_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'First name'})
    )

    last_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'Last name'})
    )

    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'placeholder': 'Email address'})
    )

    phone_number = forms.CharField(
        max_length=11,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': '09XXXXXXXXX',
            'inputmode': 'numeric',
            'pattern': '[0-9]{11}',
            'minlength': '11',
            'maxlength': '11',
        })
    )

    address = forms.CharField(
        widget=forms.Textarea(attrs={
            'placeholder': 'Address',
            'rows': 2,
        }),
        required=False,
    )

    assigned_role = forms.ModelChoiceField(
        queryset=None,  # Set in __init__
        required=True,
        empty_label='-- Select Staff Role --',
        widget=forms.Select()
    )

    branch = forms.ModelChoiceField(
        queryset=None,  # Set in __init__
        required=True,
        empty_label='-- Select Branch --',
        widget=forms.Select()
    )

    class Meta:
        """Meta options for AdminAccountCreationForm."""
        model = User
        fields = ('username', 'first_name', 'last_name', 'email',
                  'phone_number', 'address', 'assigned_role', 'branch',
                  'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Set role queryset - only staff roles, excluding superadmin again
        self.fields['assigned_role'].queryset = Role.objects.filter(
            is_staff_role=True
        ).exclude(
            code__in=['superadmin', 'user']  # Hide superadmin and user roles
        ).order_by('-hierarchy_level')

        # Set branch queryset
        self.fields['branch'].queryset = Branch.objects.filter(is_active=True)

        # Customize fields
        self.fields['username'].widget.attrs.update({'placeholder': 'Username'})
        self.fields['password1'].widget.attrs.update({'placeholder': 'Password'})
        self.fields['password2'].widget.attrs.update({'placeholder': 'Confirm password'})

    def clean_username(self):
        """Ensure the username is unique."""
        username = self.cleaned_data.get('username')
        if not username:
            raise forms.ValidationError("Username is required.")
        
        # Check for existing username (case-insensitive to be more thorough)
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("This username is already in use. Please choose another.")
        return username.lower()  # Store usernames in lowercase for consistency

    def clean_phone_number(self):
        return validate_philippines_phone(self.cleaned_data.get('phone_number', ''))

    def clean_email(self):
        """Ensure the email is unique."""
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.phone_number = self.cleaned_data.get('phone_number', '')
        user.address = self.cleaned_data.get('address', '')
        user.assigned_role = self.cleaned_data.get('assigned_role')
        user.branch = self.cleaned_data.get('branch')

        if commit:
            user.save()
        return user
