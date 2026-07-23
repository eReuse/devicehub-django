from django import forms
from django.utils.translation import gettext_lazy as _
from django.forms.models import inlineformset_factory

from user.models import Institution, InstitutionLabelSettings, InstitutionDPPSettings, FacilityClaim

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
            'name', 'logo', 'responsable_person', 'supervisor_person',
            'facility_id_uri', 'facility_description', 'country',
            'street_address', 'postal_code', 'location', 'region',
            'algorithm','registered_id', 'process_category_code',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('e.g. Acme Corp')}),
            'logo': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://example.com/logo.png'}),
            'registered_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '30-12345678-9'}),
            'process_category_code': forms.Select(attrs={'class': 'form-select'}),
            'responsable_person': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('e.g. Jane Doe')}),
            'supervisor_person': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('e.g. John Smith')}),
            'facility_id_uri': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'did:web:example.com'}),
            'facility_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': _('Describe the primary activities...')}),
            'country': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('e.g. US, ES, AR'), 'maxlength': '2'}),
            'street_address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('123 Main St')}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('10001')}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('City or Locality')}),
            'region': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('State or Province')}),
        }

class InstitutionLabelSettingsForm(forms.ModelForm):
    qr_printed_properties = forms.MultipleChoiceField(
        choices=AVAILABLE_PROPERTIES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label=_("Properties to Print")
    )

    class Meta:
        model = InstitutionLabelSettings
        fields = [
            'qr_content_type',
            'qr_label_header',
            'qr_include_logo',
            'qr_printed_properties',
            'qr_label_version',
            'qr_label_orientation',
            'qr_label_columns',
            'qr_width_mm',
            'qr_height_mm',
            'qr_font_size'
        ]
        widgets = {
            'qr_content_type': forms.RadioSelect,
            'qr_include_logo': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'qr_label_header': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Property of...'}),
            'qr_label_orientation': forms.Select(attrs={'class': 'form-select'}),
            'qr_label_columns': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '10'}),
            'qr_width_mm': forms.NumberInput(attrs={'class': 'form-control', 'min': '20', 'max': '200'}),
            'qr_height_mm': forms.NumberInput(attrs={'class': 'form-control', 'min': '20', 'max': '200'}),
            'qr_font_size': forms.NumberInput(attrs={'class': 'form-control', 'min': '4', 'max': '24'}),
        }

    def clean_qr_printed_properties(self):
        return self.cleaned_data.get('qr_printed_properties', [])

DPP_VERSION_CHOICES = [
    ('untp-0.7.0', 'UNTP v0.7.0'),
]

class InstitutionDPPSettingsForm(forms.ModelForm):
    active_dpp_standard = forms.ChoiceField(
        choices=DPP_VERSION_CHOICES,
        widget=forms.RadioSelect,
        label=_("Supported UNTP Versions"),
        required=True,
        help_text=_("Select the protocol version your backend should use to construct credentials.")
    )

    class Meta:
        model = InstitutionDPPSettings
        fields = ['api_base_url', 'signing_auth_token', 'issuer_did',
                  'active_dpp_standard', 'dpp_schema', 'dte_schema', 'dfr_schema']

    def __init__(self, *args, **kwargs):
        schemas = kwargs.pop('schemas', {})
        super().__init__(*args, **kwargs)

        def setup_schema_field(field_name, schema_list, label):
            choices = [(s['file_schema'], s['name']) for s in schema_list]

            if choices:
                self.fields[field_name] = forms.ChoiceField(
                    choices=choices,
                    label=label,
                    required=False
                )
            else:
                saved_val = getattr(self.instance, field_name, None)

                if saved_val:
                    fallback_choices = [(saved_val, f"{saved_val} (Unverified - API Unreachable)")]
                else:
                    fallback_choices = [('', _('API Unreachable - No Schema Available'))]

                self.fields[field_name] = forms.ChoiceField(
                    choices=fallback_choices,
                    label=label,
                    required=False,
                    disabled=True
                )

        setup_schema_field('dpp_schema', schemas.get('dpp', []), _("DPP Schema"))
        setup_schema_field('dte_schema', schemas.get('dte', []), _("DTE Schema"))
        setup_schema_field('dfr_schema', schemas.get('dfr', []), _("DFR Schema"))


class FacilityClaimForm(forms.ModelForm):
    class Meta:
        model = FacilityClaim
        fields = [
            'description', 'topic_code', 'admin_name', 'admin_url',
            'assessment_date', 'evidence_name', 'evidence_url'
        ]
        widgets = {
            'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('e.g., ISO 14001 Certified')}),
            'topic_code': forms.Select(attrs={'class': 'form-select'}),
            'admin_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('e.g., IRAM')}),
            'admin_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://www.example.org'}),
            'assessment_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'evidence_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('e.g., Certificate.pdf')}),
            'evidence_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://example.com/cert.pdf'}),
        }

FacilityClaimFormSet = inlineformset_factory(
    Institution,
    FacilityClaim,
    form=FacilityClaimForm,
    extra=1,
    can_delete=True
)
