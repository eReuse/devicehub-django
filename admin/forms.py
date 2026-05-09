import json
from django import forms
from django.utils.translation import gettext_lazy as _
from user.models import Institution, InstitutionSettings


class OrderingStateForm(forms.Form):
    ordering = forms.CharField()

AVAILABLE_PROPERTIES = [
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
            'street_address', 'postal_code', 'location', 'region'
        ]
        widgets = {
            'facility_description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'country': forms.TextInput(attrs={
                'placeholder': 'e.g. US, ES (2 letters)',
                'maxlength': '2',
                'class': 'form-control'
            }),
            'logo': forms.TextInput(attrs={
                'placeholder': 'https://example.com/logo.png',
                'class': 'form-control'
            }),
            'facility_id_uri': forms.URLInput(attrs={
                'placeholder': 'https://:',
                'class': 'form-control'
            }),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'responsable_person': forms.TextInput(attrs={'class': 'form-control'}),
            'supervisor_person': forms.TextInput(attrs={'class': 'form-control'}),
            'street_address': forms.TextInput(attrs={'class': 'form-control'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control'}),
            'localition': forms.TextInput(attrs={'class': 'form-control'}),
            'region': forms.TextInput(attrs={'class': 'form-control'}),
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
            'qr_printed_properties'
        ]

    def clean_qr_printed_properties(self):
        return self.cleaned_data.get('qr_printed_properties', [])
