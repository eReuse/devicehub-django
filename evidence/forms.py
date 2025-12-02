import json
import pandas as pd
import hashlib
import uuid
import os
from datetime import datetime

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from utils.device import create_property, create_doc, create_index
from utils.forms import MultipleFileField
from device.models import Device
from evidence.parse import Build
from evidence.models import SystemProperty, UserProperty
from utils.save_snapshots import move_json, save_in_disk
from utils.photo_evidence import save_photo_in_disk, get_photos_dir
from action.models import DeviceLog
from evidence.image_processing import process_image


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


class PhotoForm(forms.Form):
    photo_file = forms.FileField(
        widget=forms.ClearableFileInput(
            attrs={
                'class': 'visually-hidden',
                'id': 'file-input',
                'accept': 'image/jpeg,image/jpg,image/png,image/gif,image/webp',
            }
        ),
        label="",
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        self.photo_data = None
        self.uuid = None
        super().__init__(*args, **kwargs)

    def clean_photo_file(self):
        photo = self.cleaned_data.get('photo_file')

        if not photo:
            raise ValidationError(
                _("No photo selected"),
                code="no_input",
            )

        max_size = 10 * 1024 * 1024
        if photo.size > max_size:
            raise ValidationError(
                _("File size exceeds 10MB limit"),
                code="file_too_large",
            )

        allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp']
        content_type = photo.content_type
        if content_type not in allowed_types:
            raise ValidationError(
                _("Invalid file type. Only JPEG, PNG, GIF, and WebP images are allowed"),
                code="invalid_type",
            )

        allowed_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
        file_ext = os.path.splitext(photo.name)[1].lower()
        if file_ext not in allowed_extensions:
            raise ValidationError(
                _("Invalid file extension. Only .jpg, .jpeg, .png, .gif, and .webp are allowed"),
                code="invalid_extension",
            )

        photo.seek(0)
        file_content = photo.read()
        sha256 = hashlib.sha256(file_content).hexdigest()
        photo.seek(0)  # Reset file pointer
        name = f"{sha256}{file_ext}"

        # Check if photo already exists based on hash
        photo_path = os.path.join(
            get_photos_dir(self.user.institution.name),
            name,
        )
        if os.path.exists(photo_path):
            raise ValidationError(f"Photo already exists.")

        self.photo_data = {
            'file': photo,
            'content': file_content,
            'extension': file_ext,
            'mime_type': content_type,
            'size': photo.size,
            'original_name': photo.name,
            'name': name,
            'hash': sha256
        }
        return photo

    def save(self, commit=True):
        if not commit or not self.user or not self.photo_data:
            return

        file_path = save_photo_in_disk(self.photo_data, self.user.institution.name)

        # Process image for OCR and barcode detection
        processing_result = process_image(file_path)

        # Build document structure
        self.photo_data.pop('content', None)
        self.photo_data.pop('file', None)
        self.uuid = str(uuid.uuid4())
        algo_key = 'photo25'

        doc = {
            'uuid': self.uuid,
            'type': algo_key,
            'endTime': datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            'software': 'DeviceHub',
            'photo': self.photo_data,
            'ocr': {
                'text': processing_result.get('ocr_text'),
                'error': processing_result.get('ocr_error')
            },
            'barcodes': processing_result.get('barcodes', []),
            'barcode_error': processing_result.get('barcode_error'),
            'exif': processing_result.get('exif'),
            'exif_error': processing_result.get('exif_error'),
        }

        # Save JSON snapshot to disk
        path_name = save_in_disk(doc, self.user.institution.name)
        create_index(doc, self.user)
        move_json(path_name, self.user.institution.name)

        # Create SystemProperty with key='photo25' so photo appears in evidence list
        # Using photo hash as the value (similar to device CHID for snapshots)
        SystemProperty.objects.create(
            uuid=self.uuid,
            key=algo_key,
            value=self.photo_data['hash'],
            owner=self.user.institution,
            user=self.user
        )

        return doc
