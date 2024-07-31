import json

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from utils.forms import MultipleFileField
from evidence.parse import Build
from evidence.models import Annotation


class UploadForm(forms.Form):

    evidence_file = MultipleFileField(label=_("File"))

    def clean(self):
        self.evidences = []
        data = self.cleaned_data.get('evidence_file')
        if not data:
            return False

        for f in data:
            file_name = f.name
            file_data = f.read()
            if not file_name or not file_data:
                return False

            try:
                file_json = json.loads(file_data)
                Build(file_json, None, check=True)
                exist_annotation = Annotation.objects.filter(
                    uuid=file_json['uuid']
                ).first()

                if exist_annotation:
                    raise ValidationError("error: {} exist".format(file_name))

            except Exception:
                raise ValidationError("error in: {}".format(file_name))

            self.evidences.append((file_name, file_json))

        return True

    def save(self, user, commit=True):
        if not commit or not user:
            return

        for ev in self.evidences:
            Build(ev[1], user)
