from django import forms
from django.contrib.auth.forms import UserCreationForm
import datetime

from .models import CollectionRequest, Location, ServicePackage, User, WasteType


class ResidentRegistrationForm(UserCreationForm):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    phone_number = forms.CharField(
        max_length=15,
        validators=[User.phone_validator],
        help_text='Example: 0712345678',
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'phone_number')

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.RESIDENT   # always a resident, never chosen by the visitor
        if commit:
            user.save()
        return user



class LocationForm(forms.ModelForm):
    class Meta:
        model = Location
        fields = ('label', 'estate', 'street_address', 'landmark')




class CollectionRequestForm(forms.ModelForm):
    class Meta:
        model = CollectionRequest
        fields = ('location', 'package', 'waste_type', 'preferred_date', 'notes')
        widgets = {
            'preferred_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # A resident can only pick their own locations
        self.fields['location'].queryset = Location.objects.filter(resident=user)
        # Only active packages and waste types are offered
        self.fields['package'].queryset = ServicePackage.objects.filter(is_active=True)
        self.fields['waste_type'].queryset = WasteType.objects.filter(is_active=True)

    def clean_preferred_date(self):
        date = self.cleaned_data['preferred_date']
        if date < datetime.date.today():
            raise forms.ValidationError('Please choose today or a future date.')
        return date