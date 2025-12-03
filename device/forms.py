from django import forms
from evidence.models import SystemProperty
from evidence.image_parsing import process_photo_upload
from utils.device import create_property, create_doc, create_index
from utils.save_snapshots import move_json, save_in_disk
from evidence.forms import BasePhotoMixin


DEVICE_TYPES = [
    ("Desktop", "Desktop"),
    ("Laptop", "Laptop"),
    ("Server", "Server"),
    ("GraphicCard", "GraphicCard"),
    ("HardDrive", "HardDrive"),
    ("SolidStateDrive", "SolidStateDrive"),
    ("Motherboard", "Motherboard"),
    ("NetworkAdapter", "NetworkAdapter"),
    ("Processor", "Processor"),
    ("RamModule", "RamModule"),
    ("SoundCard", "SoundCard"),
    ("Display", "Display"),
    ("Battery", "Battery"),
    ("Camera", "Camera"),
]


class DeviceMainForm(BasePhotoMixin):
    type = forms.ChoiceField(choices = DEVICE_TYPES, required=False)
    amount = forms.IntegerField(required=False, initial=1)
    custom_id = forms.CharField(required=False, label="Custom ID")

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

    def process_photo_upload(self, user=None):
        doc = process_photo_upload(self.photo_data_cache, user)

        custom_id_val = self.cleaned_data.get('custom_id')

        if doc and custom_id_val:
            SystemProperty.objects.create(
                uuid=doc['uuid'],
                key='CUSTOM_ID',
                value=custom_id_val,
                owner=self.user.institution,
                user=self.user
            )

        return doc


class DeviceAttributeForm(forms.Form):
    name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Attribute Name (e.g. CPU)'})
    )
    value = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Attribute Value (e.g. i5-6200U)'})
    )


def save_device_data(main_data, attribute_formset, user, commit=True):
    row = {}
    if main_data.get("type"):
        row["type"] = main_data["type"]
    if main_data.get("amount"):
        row["amount"] = main_data["amount"]
    if main_data.get("custom_id"):
        row["CUSTOM_ID"] = main_data["custom_id"]

    for form in attribute_formset:
        if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
            name = form.cleaned_data.get("name")
            value = form.cleaned_data.get("value", "")
            if name:
                row[name] = value

    doc = create_doc(row)

    if not commit:
        return doc

    path_name = save_in_disk(doc, user.institution.name, place="placeholder")
    create_index(doc, user)
    create_property(doc, user, commit=commit)
    move_json(path_name, user.institution.name, place="placeholder")

    return doc


DeviceAttributeFormSet = forms.formset_factory(DeviceAttributeForm, extra=1, can_delete=True)
