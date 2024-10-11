from django import forms


class SettingsForm(forms.Form):
    token = forms.ChoiceField(
        choices = []
    )
    erasure = forms.ChoiceField(
        choices = [(0, 'Not erasure'),
            ('erasure1', 'Erasure easy'),
            ('erasure2', 'Erasure mediom'),
            ('erasure3', 'Erasure hard'),
        ],
    )

    def __init__(self, *args, **kwargs):
        tokens = kwargs.pop('tokens')
        super().__init__(*args, **kwargs)
        tk = [(str(x.token), x.tag) for x in tokens]
        self.fields['token'].choices = tk
