import json
import pandas as pd

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from utils.device import create_annotation, create_doc, create_index
from utils.forms import MultipleFileField
from device.models import Device
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


class UserTagForm(forms.Form):
    tag = forms.CharField(label=_("Tag"))

    def __init__(self, *args, **kwargs):
        self.uuid = kwargs.pop('uuid', None)
        super().__init__(*args, **kwargs)

    def clean(self):
        data = self.cleaned_data.get('tag')
        if not data:
            return False
        self.tag = data
        return True

    def save(self, user, commit=True):
        if not commit:
            return

        Annotation.objects.create(
            uuid=self.uuid,
            owner=user,
            type=Annotation.Type.SYSTEM,
            key='CUSTOM_ID',
            value=self.tag
        )


class ImportForm(forms.Form):
    file_import = forms.FileField(label=_("File to import"))

    def __init__(self, *args, **kwargs):

        self.rows = []
        self.properties = {}
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)

    def clean_file_import(self):
        data = self.cleaned_data["file_import"]

        self.file_name = data.name
        df = pd.read_excel(data)
        df.fillna('', inplace=True)

        data_pd = df.to_dict(orient='index')

        if not data_pd or df.last_valid_index() is None:
            self.exception(_("The file you try to import is empty!"))

        for n in data_pd.keys():
            if 'type' not in [x.lower() for x in data_pd[n]]:
                raise ValidationError("You need a column with name 'type'")
        
            for k, v in data_pd[n].items():
                if k.lower() == "type":
                    if v not in Device.Types.values:
                        raise ValidationError("{} is not a valid device".format(v))
                
            self.rows.append(data_pd[n])

        return data


    def save(self, commit=True):
        table = []
        for row in self.rows:
            doc = create_doc(row)
            annotation = create_annotation(doc, self.user)
            table.append((doc, annotation))

        if commit:
            for doc, cred in table:
              cred.save()
              create_index(doc)
            return table

        return
