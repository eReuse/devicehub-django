import json
from django import forms
from django.utils.translation import gettext_lazy as _
from user.models import Institution, InstitutionSettings


class OrderingStateForm(forms.Form):
    ordering = forms.CharField()

AVAILABLE_PROPERTIES = [
    ('ID', _('Short ID')),
    ('manufacturer', _('Manufacturer')),
    ('model', _('Model')),
    ('serial', _('Serial Number')),
    ('cpu_model', _('CPU Model')),
    ('ram_total', _('Total RAM')),
    ('ram_type', _('RAM Type')),
    ('drive', _('Storage Drive')),
    ('type', _('Form Factor (Type)')),
]

class InstitutionForm(forms.ModelForm):
    class Meta:
        model = Institution
        fields = [
            'name',
            'logo', 'responsable_person', 'supervisor_person',
            'facility_id_uri', 'facility_description', 'country',
            'street_address', 'postal_code', 'locality', 'region'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('e.g. Acme Corp')}),
            'logo': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://example.com/logo.png'}),
            'responsable_person': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('e.g. Jane Doe')}),
            'supervisor_person': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('e.g. John Smith')}),
            'facility_id_uri': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'did:web:example.com'}),
            'facility_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': _('Describe the primary activities...')}),

            'country': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('e.g. US, ES, DE'), 'maxlength': '2'}),
            'street_address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('123 Main St')}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('10001')}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('City or Locality')}),
            'region': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('State or Province')}),
        }


class InstitutionSettingsForm(forms.ModelForm):
    qr_printed_properties = forms.MultipleChoiceField(
        choices=AVAILABLE_PROPERTIES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label=_("Properties to Print")
    )

    class Meta:
        model = InstitutionSettings
        fields = [
            'qr_content_type',
            'qr_label_header',
            'qr_include_logo',
            'qr_printed_properties',

            'algorithm', 'issuer_did',
            'signing_service_domain', 'signing_auth_token',
            'device_dpp_schema', 'untp_drf_schema'
        ]
        widgets = {
            'qr_content_type': forms.RadioSelect,
            'qr_include_logo': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'qr_label_header': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Property of...'}),
        }

    def clean_qr_printed_properties(self):
        return self.cleaned_data.get('qr_printed_properties', [])
