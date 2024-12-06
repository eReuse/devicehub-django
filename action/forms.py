from django import forms
from .models import State


class AddStateForm(forms.Form):
    add_note = forms.BooleanField(required=False)
    note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 4, 'maxlength': 200, 'placeholder': 'Max 200 characters'}),
    )
    state_id = forms.IntegerField(required=True, widget=forms.HiddenInput())
    snapshot_uuid = forms.UUIDField(required=True, widget=forms.HiddenInput())
   

    def clean(self):
        cleaned_data = super().clean()
        add_note = cleaned_data.get('add_note')
        note = cleaned_data.get('note')

        if add_note == True and not note:
            self.add_error('note', 'Please enter a note if you checked "Add a note".')
        return cleaned_data