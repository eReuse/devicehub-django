import json
import pandas as pd

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from utils.device import create_property, create_doc, create_index
from utils.forms import MultipleFileField
from device.models import Device
from evidence.parse import Build
from evidence.models import SystemProperty, UserProperty
from utils.save_snapshots import move_json, save_in_disk
from action.models import DeviceLog


class UploadForm(forms.Form):
    evidence_file = MultipleFileField()

    def clean_evidence_file(self):
        self.evidences = []
        data = self.cleaned_data.get('evidence_file')
        if not data:
            raise ValidationError(
                _("No snapshot selected"),
                code="no_input",
            )

        for f in data:
            file_name = f.name
            file_data = f.read()
            if not file_name or not file_data:
                return False

            try:
                file_json = json.loads(file_data)
                snap = Build(file_json, None, check=True)
                exists_property = SystemProperty.objects.filter(
                    uuid=snap.uuid
                ).first()

                if exists_property:
                    raise ValidationError(
                        _("The snapshot already exists"),
                        code="duplicate_snapshot",
                    )

            #Catch any error and display it as Validation Error so the Form handles it
            except Exception as e:
                raise ValidationError(
                    _("Error on '%(file_name)s': %(error)s"),
                    code="error",
                    params={"file_name": file_name, "error": getattr(e, 'message', str(e))},
                )
            self.evidences.append((file_name, file_json))

        return True

    def save(self, user, commit=True):
        if not commit or not user:
            return

        for ev in self.evidences:
            path_name = save_in_disk(ev[1], user.institution.name)
            build = Build
            file_json = ev[1]
            build(file_json, user)
            move_json(path_name, user.institution.name)


class UserTagForm(forms.Form):
    tag = forms.CharField(label=_("Tag"))

    def __init__(self, *args, **kwargs):
        self.pk = None
        self.uuid = kwargs.pop('uuid', None)
        self.user = kwargs.pop('user')
        instance = SystemProperty.objects.filter(
            uuid=self.uuid,
            key='CUSTOM_ID',
            owner=self.user.institution
        ).first()

        if instance:
            kwargs["initial"]["tag"] = instance.value
            self.pk = instance.pk

        super().__init__(*args, **kwargs)

    def clean(self):
        data = self.cleaned_data.get('tag')
        if not data:
            return False
        self.tag = data
        self.instance = SystemProperty.objects.filter(
            uuid=self.uuid,
            key='CUSTOM_ID',
            owner=self.user.institution
        ).first()

        return True

    def save(self, user, commit=True):
        if not commit:
            return

        if self.instance:
            old_value = self.instance.value
            if not self.tag:
                message =_("<Deleted> Evidence Tag. Old Value: '{}'").format(old_value)
                self.instance.delete()
            else:
                self.instance.value = self.tag
                self.instance.save()
                if old_value != self.tag:
                    message=_("<Updated> Evidence Tag. Old Value: '{}'. New Value: '{}'").format(old_value, self.tag)
        else:
            message =_("<Created> Evidence Tag. Value: '{}'").format(self.tag)
            SystemProperty.objects.create(
                uuid=self.uuid,
                key='CUSTOM_ID',
                value=self.tag,
                owner=self.user.institution,
                user=self.user
            )
        
        DeviceLog.objects.create(
                snapshot_uuid=self.uuid,
                event= message,
                user=self.user,
                institution=self.user.institution
            )


class ImportForm(forms.Form):
    file_import = forms.FileField(
        widget=forms.ClearableFileInput(
            attrs={
                'class': 'visually-hidden',
                'id': 'file-input',
            }
        ),
        label="",
    )

    def __init__(self, *args, **kwargs):

        self.rows = []
        self.properties = {}
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)

    def clean_file_import(self):
        data = self.cleaned_data["file_import"]

        self.file_name = data.name

        try:
            df = pd.read_excel(data)
        except Exception as e:
            raise ValidationError(
                _("Error on '%(file_name)s': Invalid File"),
                params={"file_name": self.file_name}
            )

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
            property = create_property(doc, self.user)
            table.append((doc, property))

        if commit:
            for doc, cred in table:
                path_name = save_in_disk(doc, self.user.institution.name, place="placeholder")

                cred.save()
                create_index(doc, self.user)
                move_json(path_name, self.user.institution.name, place="placeholder")
            return table

        return


class EraseServerForm(forms.Form):
    erase_server = forms.BooleanField(label=_("Is a Erase Server"), required=False)

    def __init__(self, *args, **kwargs):
        self.pk = None
        self.uuid = kwargs.pop('uuid', None)
        self.user = kwargs.pop('user')
        instance = UserProperty.objects.filter(
            uuid=self.uuid,
            type=UserProperty.Type.ERASE_SERVER,
            key='ERASE_SERVER',
            owner=self.user.institution
        ).first()

        if instance:
            kwargs["initial"]["erase_server"] = instance.value
            self.pk = instance.pk

        super().__init__(*args, **kwargs)

    def clean(self):
        self.erase_server = self.cleaned_data.get('erase_server', False)
        self.instance = UserProperty.objects.filter(
            uuid=self.uuid,
            type=UserProperty.Type.ERASE_SERVER,
            key='ERASE_SERVER',
            owner=self.user.institution
        ).first()

        return True

    def save(self, user, commit=True):
        if not commit:
            return

        if not self.erase_server:
            if self.instance:
                self.instance.delete()
            return

        if self.instance:
            return

        UserProperty.objects.create(
            uuid=self.uuid,
            type=UserProperty.Type.ERASE_SERVER,
            key='ERASE_SERVER',
            value=self.erase_server,
            owner=self.user.institution,
            user=self.user
        )
