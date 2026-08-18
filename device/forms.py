import re
from django import forms
from django.db.models import Q
from evidence.image_processing import process_photo_upload
from evidence.models import SystemProperty, RootAlias
from utils.device import create_property, create_doc, create_index
from utils.save_snapshots import move_json, save_in_disk
from evidence.forms import BasePhotoMixin, UserAliasForm
from django.utils.translation import gettext_lazy as _


class DeviceMainForm(BasePhotoMixin):
    type = forms.ChoiceField(choices=[])
    amount = forms.IntegerField(initial=1, min_value=1)
    custom_id = forms.CharField(required=False, label=_("Custom ID"))

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.device_types = kwargs.pop('device_types', [])
        super().__init__(*args, **kwargs)
        if self.device_types:
            self.fields['type'].choices = [("", _("Select One"))] + list(self.device_types)

    def clean(self):
        if not self.device_types:
            raise forms.ValidationError(_("You need select one type of product"))
        return super().clean()

    def clean_custom_id(self):
        custom_id = self.cleaned_data.get('custom_id')

        if custom_id and self.user:
            _custom_id = f"custom_id:{custom_id}"
            exists = RootAlias.objects.filter(owner=self.user.institution).filter(
                Q(root__iexact=_custom_id) | Q(alias__iexact=_custom_id)
            ).exists()

            if exists:
                raise forms.ValidationError(_("This Custom ID is already in use by another device."))

        return custom_id

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

        # custom_id is now guaranteed to be safe and duplicate-free
        custom_id = self.cleaned_data.get('custom_id')

        photo_cache = getattr(self, 'photo_data_cache', None)
        photo_doc = process_photo_upload(photo_cache, self.user)

        amount = self.cleaned_data.get('amount') or 1

        # for now, if a photo is uploaded, only create 1 device
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

            alias_root_target = None
            if custom_id:
                alias_root_target = custom_id
            elif photo_prop:
                alias_root_target = device_web_id

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
        widget=forms.TextInput(attrs={'placeholder': 'Attribute Name', 'class': 'form-control'})
    )
    value = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Value', 'class': 'form-control'})
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
            if name and value.strip():
                row[name] = value.strip()

    doc = create_doc(row)

    if not commit:
        return doc

    path_name = save_in_disk(doc, user.institution.name, place="placeholder")
    create_index(doc, user)
    prop = create_property(doc, user, commit=commit)
    move_json(path_name, user.institution.name, place="placeholder")

    return doc, prop


DeviceAttributeFormSet = forms.formset_factory(DeviceAttributeForm, extra=1, can_delete=True)
