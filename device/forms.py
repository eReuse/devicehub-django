from django import forms
from utils.device import create_property, create_doc, create_index
from utils.save_snapshots import move_json, save_in_disk
from django.utils.translation import gettext_lazy as _
#TODO: translate device types
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


class DeviceForm(forms.Form):
    type = forms.ChoiceField(choices = DEVICE_TYPES, required=False, label= _(u"Type"))
    amount = forms.IntegerField(required=False, initial=1, label= _(u"Amount"))
    custom_id = forms.CharField(required=False, label=_(u"Custom id"))
    name = forms.CharField(required=False, label= _(u"Name"))
    value = forms.CharField(required=False, label=_(u"Value"))


class BaseDeviceFormSet(forms.BaseFormSet):
    def clean(self):
        for x in self.cleaned_data:
            if x.get("amount"):
                return True
        return False
        
    def save(self, user, commit=True):
        self.user = user
        row = {}
        for f in self.forms:
            d = f.cleaned_data
            if not d:
                continue

            if d.get("type"):
                row["type"] = d["type"]
            if d.get("amount"):
                row["amount"] = d["amount"]
            if d.get("name"):
                row[d["name"]] = d.get("value", '')
            if d.get("custom_id"):
                row['CUSTOM_ID']= d["custom_id"]

        doc = create_doc(row)
        if not commit:
            return doc
        
        path_name = save_in_disk(doc, self.user.institution.name, place="placeholder")
        create_index(doc, self.user)
        create_property(doc, user, commit=commit)
        move_json(path_name, self.user.institution.name, place="placeholder")
        
        return doc


DeviceFormSet = forms.formset_factory(form=DeviceForm, formset=BaseDeviceFormSet, extra=1)

