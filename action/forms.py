from django import forms
from .models import State


class ChangeStateForm(forms.Form):
    previous_state = forms.CharField(widget=forms.HiddenInput())
    snapshot_uuid = forms.UUIDField(widget=forms.HiddenInput())
    new_state = forms.CharField(widget=forms.HiddenInput())


class AddNoteForm(forms.Form):
    snapshot_uuid = forms.UUIDField(widget=forms.HiddenInput())
    note = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={'rows': 4, 'maxlength': 200, 'placeholder': 'Max 200 characters'}),
    )
