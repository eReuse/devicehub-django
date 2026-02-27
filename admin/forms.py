import json
from django import forms
from django.utils.translation import gettext_lazy as _
from user.models import Institution, InstitutionSettings


class OrderingStateForm(forms.Form):
    ordering = forms.CharField()


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
                'placeholder': 'https:// or did:web:',
                'class': 'form-control'
            }),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'responsable_person': forms.TextInput(attrs={'class': 'form-control'}),
            'supervisor_person': forms.TextInput(attrs={'class': 'form-control'}),
            'street_address': forms.TextInput(attrs={'class': 'form-control'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control'}),
            'locality': forms.TextInput(attrs={'class': 'form-control'}),
            'region': forms.TextInput(attrs={'class': 'form-control'}),
        }


class InstitutionSettingsForm(forms.ModelForm):
    schema_config_json = forms.CharField(
        label=_("Schema Configuration (JSON)"),
        widget=forms.Textarea(attrs={
            'rows': 5,
            'class': 'form-control font-monospace',
            'placeholder': '{"dpp": "dpp_v1.json", "traceability": "trace_v1.json"}'
        }),
        help_text=_("Map credential types to schema filenames. Must be valid JSON."),
        required=False
    )

    class Meta:
        model = InstitutionSettings
        fields = [
            'algorithm',
            'issuer_did',
            'api_base_url',
            'signing_auth_token',
            # 'schema_config' is handled by schema_config_json
        ]
        widgets = {
            'signing_auth_token': forms.PasswordInput(render_value=True, attrs={'class': 'form-control'}),
            'issuer_did': forms.TextInput(attrs={
                'placeholder': 'did:web:example.com',
                'class': 'form-control'
            }),
            'api_base_url': forms.URLInput(attrs={
                'placeholder': 'https://idhub.example.com/api/v1/',
                'class': 'form-control'
            }),
            'algorithm': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # If the instance exists and has config, load it into the text field
        if self.instance and self.instance.pk and self.instance.schema_config:
            self.fields['schema_config_json'].initial = json.dumps(self.instance.schema_config, indent=2)

    def clean_schema_config_json(self):
        """Validate that the text input is actually valid JSON"""
        data = self.cleaned_data.get('schema_config_json')
        if not data:
            return {}
        try:
            json_data = json.loads(data)
            if not isinstance(json_data, dict):
                raise forms.ValidationError(_("Configuration must be a JSON object (dictionary)."))
            return json_data
        except json.JSONDecodeError:
            raise forms.ValidationError(_("Invalid JSON format. Please check syntax."))

    def save(self, commit=True):
        # Move the cleaned JSON string back into the actual model field
        instance = super(InstitutionSettingsForm, self).save(commit=False)
        instance.schema_config = self.cleaned_data['schema_config_json']
        if commit:
            instance.save()
        return instance
