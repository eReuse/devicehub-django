from django import forms
from django.utils.translation import gettext_lazy as _
from user.models import Institution, InstitutionSettings


class OrderingStateForm(forms.Form):
    ordering = forms.CharField()


class InstitutionForm(forms.ModelForm):
    class Meta:
        model = Institution
        fields = [
            'logo', 'responsable_person', 'supervisor_person',
            'facility_id_uri', 'facility_description', 'country',
            'street_address', 'postal_code', 'locality', 'region'
        ]
        widgets = {
            'facility_description': forms.Textarea(attrs={'rows': 3}),
            'country': forms.TextInput(attrs={'placeholder': 'e.g. US, DE, AU'}),
            'logo': forms.TextInput(attrs={'placeholder': 'https://example.com/logo.png'}),
        }

class InstitutionSettingsForm(forms.ModelForm):
    class Meta:
        model = InstitutionSettings
        fields = [
            'algorithm', 'issuer_did',
            'signing_service_domain', 'signing_auth_token',
            'device_dpp_schema', 'untp_drf_schema'
        ]
        widgets = {
            'signing_auth_token': forms.PasswordInput(render_value=True),
            'issuer_did': forms.TextInput(attrs={'placeholder': 'did:web:example.com'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
