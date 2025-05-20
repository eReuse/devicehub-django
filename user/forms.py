from django import forms
from django.utils.translation import gettext_lazy as _

class SettingsForm(forms.Form):
    token = forms.ChoiceField(
        choices = []
    )
    erasure = forms.ChoiceField(
        choices = [(0, _('Not erasure')),
            ('basic', _('Erasure Basic')),
            ('baseline', _('Erasure Baseline')),
            ('enhanced', _('Erasure Enhanced')),
        ],
    )

    def __init__(self, *args, **kwargs):
        tokens = kwargs.pop('tokens')
        super().__init__(*args, **kwargs)
        tk = [(str(x.token), x.tag) for x in tokens]
        self.fields['token'].choices = tk
