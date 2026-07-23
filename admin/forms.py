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
    facility_id_uri = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'did:web:example.com'})
    )

    class Meta:
        model = Institution
        fields = [
            'name', 'logo', 'responsable_person', 'supervisor_person',
            'facility_id_uri', 'facility_description', 'country',
            'street_address', 'postal_code', 'location', 'region',
            'algorithm', 'registered_id', 'process_category_code',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': _('e.g. Acme Corp')}),
            'logo': forms.URLInput(attrs={'placeholder': 'https://example.com/logo.png'}),
            'registered_id': forms.TextInput(attrs={'placeholder': '30-12345678-9'}),
            'responsable_person': forms.TextInput(attrs={'placeholder': _('e.g. Jane Doe')}),
            'supervisor_person': forms.TextInput(attrs={'placeholder': _('e.g. John Smith')}),
            'facility_description': forms.Textarea(attrs={'rows': 3, 'placeholder': _('Describe the primary activities...')}),
            'country': forms.TextInput(attrs={'placeholder': _('e.g. US, ES, AR'), 'maxlength': '2'}),
            'street_address': forms.TextInput(attrs={'placeholder': _('123 Main St')}),
            'postal_code': forms.TextInput(attrs={'placeholder': _('10001')}),
            'location': forms.TextInput(attrs={'placeholder': _('City or Locality')}),
            'region': forms.TextInput(attrs={'placeholder': _('State or Province')}),
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
            'qr_content_type', 'qr_label_header', 'qr_include_logo',
            'qr_printed_properties', 'qr_label_version', 'qr_label_orientation',
            'qr_label_columns', 'qr_width_mm', 'qr_height_mm', 'qr_font_size'
        ]
        widgets = {
            'qr_content_type': forms.RadioSelect,
            'qr_include_logo': forms.CheckboxInput(attrs={'role': 'switch'}),
            'qr_label_header': forms.TextInput(attrs={'placeholder': 'Property of...'}),
            'qr_label_columns': forms.NumberInput(attrs={'min': '1', 'max': '10'}),
            'qr_width_mm': forms.NumberInput(attrs={'min': '20', 'max': '200'}),
            'qr_height_mm': forms.NumberInput(attrs={'min': '20', 'max': '200'}),
            'qr_font_size': forms.NumberInput(attrs={'min': '4', 'max': '24'}),
        }

    def clean_qr_printed_properties(self):
        data = self.cleaned_data.get('qr_printed_properties', [])
        return data


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
        widgets = {
            'signing_auth_token': forms.PasswordInput(render_value=True),
        }

    def __init__(self, *args, **kwargs):
        schemas = kwargs.pop('schemas', {})
        super().__init__(*args, **kwargs)

        self._disabled_schema_fields = []

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
                self._disabled_schema_fields.append(field_name)

        setup_schema_field('dpp_schema', schemas.get('dpp', []), _("DPP Schema"))
        setup_schema_field('dte_schema', schemas.get('dte', []), _("DTE Schema"))
        setup_schema_field('dfr_schema', schemas.get('dfr', []), _("DFR Schema"))

    def clean(self):
        cleaned_data = super().clean()

        for field_name in self._disabled_schema_fields:
            if field_name not in cleaned_data or not cleaned_data[field_name]:
                cleaned_data[field_name] = getattr(self.instance, field_name, None)

        return cleaned_data


class FacilityClaimForm(forms.ModelForm):
    class Meta:
        model = FacilityClaim
        fields = [
            'description', 'topic_code', 'admin_name', 'admin_url',
            'assessment_date', 'evidence_name', 'evidence_url'
        ]
        widgets = {
            'description': forms.TextInput(attrs={'placeholder': _('e.g., ISO 14001 Certified')}),
            'admin_name': forms.TextInput(attrs={'placeholder': _('e.g., IRAM')}),
            'admin_url': forms.URLInput(attrs={'placeholder': 'https://www.example.org'}),
            'assessment_date': forms.DateInput(attrs={'type': 'date'}),
            'evidence_name': forms.TextInput(attrs={'placeholder': _('e.g., Certificate.pdf')}),
            'evidence_url': forms.URLInput(attrs={'placeholder': 'https://example.com/cert.pdf'}),
        }


FacilityClaimFormSet = inlineformset_factory(
    Institution,
    FacilityClaim,
    form=FacilityClaimForm,
    extra=1,
    can_delete=True
)
