import json
import pandas as pd
import hashlib
import os

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from utils.device import create_property, create_doc, create_index
from utils.forms import MultipleFileField
from device.models import Device
from evidence.parse import Build
from evidence.models import SystemProperty, UserProperty, RootAlias
from evidence.image_processing import process_photo_upload
from utils.save_snapshots import move_json, save_in_disk
from utils.photo_evidence import get_photos_dir
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


class UserAliasForm(forms.Form):
    root = forms.CharField(label=_("Alias"), required=True)

    def __init__(self, *args, **kwargs):
        self.uuid = kwargs.pop('uuid', None)
        self.user = kwargs.pop('user')
        self.sysprop = kwargs.pop('instance', None)
        self.instance = None
        if self.sysprop:
            self.instance = RootAlias.objects.filter(
                owner=self.sysprop.owner,
                alias=self.sysprop.value
            ).first()

        if self.instance and self.instance.root != self.instance.alias:
            # self-reference (alias==root) is the "empty" state; show the
            # field blank so the user can type a fresh alias.
            root = self.instance.root
            if "custom_id" == root.split(":")[0]:
                root = root.split(":")[1]

            kwargs.setdefault("initial", {})["root"] = root

        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        self.root_alias = self.cleaned_data.get('root', '').lower()

        if self.root_alias == self.sysprop.value:
            txt = _("This alias is the same as the current evidence.")
            self.add_error('', txt)
            return cleaned_data

        # Resolve the final root id (fall through to custom_id if the typed
        # value is not itself a SystemProperty).
        sp = SystemProperty.objects.filter(owner=self.sysprop.owner)
        if sp.filter(value=self.root_alias).first():
            resolved_root = self.root_alias
        else:
            resolved_root = "custom_id:{}".format(self.root_alias)

        # Depth-1 invariant, rule 2: current evidence cannot be re-rooted
        # if other aliases already depend on it as root.
        if RootAlias.has_dependents(self.user.institution, self.sysprop.value):
            txt = _("To prevent loops, current evidence cannot be linked to another Alias Identifier because it is already linked by other evidences.")
            self.add_error('', txt)
            return cleaned_data

        # Depth-1 invariant, rule 1: target must itself be terminal.
        if not RootAlias.is_terminal_root(self.user.institution, resolved_root):
            txt = _("Target alias '{}' is not a terminal root; pick one that is not itself aliased.").format(resolved_root)
            self.add_error('', txt)
            return cleaned_data

        self._resolved_root = resolved_root
        return True

    def save(self, commit=True):
        if not commit:
            return

        root_alias = self._resolved_root
        old_value = self.instance.root if self.instance else None

        self.instance = RootAlias.set_alias(
            owner=self.sysprop.owner,
            alias=self.sysprop.value,
            new_root=root_alias,
            user=self.instance.user if self.instance else None,
        )

        if old_value is None:
            message = _("<Created> Evidence alias. Value: '{}'").format(root_alias)
            self.log(message)
            return self.instance

        if old_value == root_alias:
            return

        message = _("<Updated> Evidence alias. Old Value: '{}'. New Value: '{}'").format(
            old_value, root_alias
        )
        self.log(message)

    def log(self, message):
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

        df = df.apply(lambda col: col.map(lambda v: v.strip() if isinstance(v, str) else v))
        df.replace('', pd.NA, inplace=True)
        df.dropna(how='all', inplace=True)
        df = df.astype(object).fillna('')

        data_pd = df.to_dict(orient='index')

        if not data_pd or df.last_valid_index() is None:
            raise ValidationError(_("The file you try to import is empty"))

        for n in data_pd.keys():
            if 'type' not in [x.lower() for x in data_pd[n]]:
                raise ValidationError(_("You need a column with name 'type'"))

            for k, v in data_pd[n].items():
                if k.lower() == "type":
                    if v not in Device.Types.values:
                        msg = _("is not a valid device")
                        raise ValidationError("{} {}".format(v, msg))

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

                create_index(doc, self.user)
                cred.save()
                move_json(path_name, self.user.institution.name, place="placeholder")
            return table

        return


class EraseServerForm(forms.Form):
    erase_server = forms.BooleanField(label=_("Is a Erase Server"), required=False)

    def __init__(self, *args, **kwargs):
        self.pk = None
        self.uuid = kwargs.pop('uuid', None)
        self.user = kwargs.pop('user')
        kwargs.pop('instance', None)
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

class BasePhotoMixin(forms.Form):
    photo_file = forms.FileField(
        required=False,
        label="",
        widget=forms.ClearableFileInput(attrs={
            'class': 'visually-hidden',
            'id': 'file-input',
            'accept': 'image/jpeg,image/jpg,image/png,image/gif,image/webp',
        })
    )

    def clean_photo_file(self):
        photo = self.cleaned_data.get('photo_file')
        if not photo:
            return None

        max_size = 10 * 1024 * 1024
        if photo.size > max_size:
            raise ValidationError(_("File size exceeds 10MB limit"), code="file_too_large")

        allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp']
        if photo.content_type not in allowed_types:
            raise ValidationError(_("Invalid file type."), code="invalid_type")

        allowed_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
        file_ext = os.path.splitext(photo.name)[1].lower()
        if file_ext not in allowed_extensions:
            raise ValidationError(_("Invalid file extension."), code="invalid_extension")

        photo.seek(0)
        file_content = photo.read()
        sha256 = hashlib.sha256(file_content).hexdigest()
        photo.seek(0)

        name = f"{sha256}{file_ext}"

        # Check if photo already exists based on hash
        photo_path = os.path.join(
            get_photos_dir(self.user.institution.name),
            name,
        )
        if os.path.exists(photo_path):
            raise ValidationError(_("Photo already exists."))

        self.photo_data_cache = {
            'file': photo,
            'content': file_content,
            'extension': file_ext,
            'mime_type': photo.content_type,
            'size': photo.size,
            'original_name': photo.name,
            'name': name,
            'hash': sha256
        }

        return photo


class PhotoForm(BasePhotoMixin, forms.Form):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        if not commit:
            return None
        doc = process_photo_upload(self.photo_data_cache, user=self.user)
        return doc
