import re
from django import forms
from evidence.image_processing import process_photo_upload
from evidence.models import SystemProperty
from utils.device import create_property, create_doc, create_index
from utils.save_snapshots import move_json, save_in_disk
from evidence.forms import BasePhotoMixin, UserAliasForm


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
    type = forms.ChoiceField(choices=DEVICE_TYPES, required=False)
    amount = forms.IntegerField(required=False, initial=1, min_value=1)
    custom_id = forms.CharField(required=False, label="Custom ID")

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

    def generate_next_id(self, base_id, offset):
        if offset == 0: return base_id
        match = re.search(r'(\d+)$', base_id)
        if match:
            num_str = match.group(1)
            prefix = base_id[:-len(num_str)]
            new_num = int(num_str) + offset
            return f"{prefix}{str(new_num).zfill(len(num_str))}"
        return f"{base_id}-{offset + 1}"

    def save(self, attribute_formset):
        if not self.user:
            raise ValueError("User is required to save devices.")

        photo_cache = getattr(self, 'photo_data_cache', None)
        photo_doc = process_photo_upload(photo_cache, self.user)

        amount = self.cleaned_data.get('amount') or 1
        custom_id = self.cleaned_data.get('custom_id')

        #for now, if a photo is uploaded, only create 1 device
        if photo_cache or custom_id:
            amount = 1

        photo_prop = None
        if photo_doc:
            photo_prop = SystemProperty.objects.filter(
                uuid=photo_doc['uuid'], key='photo25'
            ).first()

        created_docs = []
        for i in range(amount):
            device_data = self.cleaned_data.copy()

            device_doc, device_prop = save_device_data(
                main_data=device_data,
                attribute_formset=attribute_formset,
                user=self.user
            )
            created_docs.append(device_doc)

            device_web_id = device_doc.get('WEB_ID', None)
            alias_root_target = custom_id or (device_web_id if photo_prop else None)

            if not alias_root_target:
                continue

            if custom_id and device_prop:
                self._create_alias(device_prop, alias_root_target)

            if photo_prop:
                self._create_alias(photo_prop, alias_root_target)

            device_prop = SystemProperty.objects.filter(
                uuid=device_doc['uuid']
            ).first()

        return created_docs

    def _create_alias(self, prop_instance, root_val):
        form = UserAliasForm(
            data={'root': root_val},
            user=self.user,
            uuid=prop_instance.uuid,
            instance=prop_instance
        )
        if form.is_valid():
            form.save()


class DeviceAttributeForm(forms.Form):
    name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Attribute (e.g. CPU)'})
    )
    value = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Value (e.g. i5-6200U)'})
    )


def save_device_data(main_data, attribute_formset, user, commit=True):
    row = {}
    if main_data.get("type"):
        row["type"] = main_data["type"]
    if main_data.get("name"):
        row["name"] = main_data["name"]

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
    prop = create_property(doc, user, commit=commit)
    move_json(path_name, user.institution.name, place="placeholder")

    return doc, prop


DeviceAttributeFormSet = forms.formset_factory(DeviceAttributeForm, extra=1, can_delete=True)
