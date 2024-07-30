import json

from django import forms
from django.utils.translation import gettext_lazy as _
from evidence.parse import Build


class UploadForm(forms.Form):

    evidence_file = forms.FileField(label=_("File"))

    def clean(self):
        data = self.cleaned_data.get('evidence_file')
        if not data:
            return False

        self.file_name = data.name
        self.file_data = data.read()
        if not self.file_name or not self.file_data:
            return False
        try:
            self.file_json = json.loads(self.file_data)
        except Exception:
            return False

        return True

    def save(self, user, commit=True):
        if not commit or not user:
            return

        evidence = Build(self.file_json, user)
        return evidence
