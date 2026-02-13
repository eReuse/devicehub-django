from django import forms
from django.utils.translation import gettext_lazy as _
from .models import State, DeviceLog


class ChangeStateForm(forms.Form):
    previous_state = forms.CharField(widget=forms.HiddenInput())
    snapshot_uuid = forms.UUIDField(widget=forms.HiddenInput())
    new_state = forms.CharField(widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        new_state = self.cleaned_data['new_state']
        snapshot_uuid = self.cleaned_data['snapshot_uuid']


        self.instance = State(
            snapshot_uuid=snapshot_uuid,
            state=new_state,
            user=self.user,
            institution=self.user.institution,
        )
        if commit:
            self.instance.save()
            self.save_log()

    def save_log(self):
        new_state = self.cleaned_data['new_state']
        previous_state = self.cleaned_data['previous_state']
        message = _("<Created> State '{}'. Previous State: '{}'").format(new_state, previous_state)
        DeviceLog.objects.create(
            snapshot_uuid=self.instance.snapshot_uuid,
            event=message,
            user=self.user,
            institution=self.user.institution,
        )


class AddNoteForm(forms.Form):
    snapshot_uuid = forms.UUIDField(widget=forms.HiddenInput())
    note = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={'rows': 4, 'maxlength': 200, 'placeholder': 'Max 200 characters'}),
    )
