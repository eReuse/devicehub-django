from django import forms
from utils.device import create_annotation, create_doc, create_index


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
    type = forms.ChoiceField(choices = DEVICE_TYPES, required=False)
    amount = forms.IntegerField(required=False, initial=1)
    customer_id = forms.CharField(required=False)
    name = forms.CharField(required=False)
    value = forms.CharField(required=False)


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
            if d.get("customer_id"):
                row['CUSTOMER_ID']= d["customer_id"]

        doc = create_doc(row)
        if not commit:
            return doc

        create_index(doc, self.user)
        create_annotation(doc, user, commit=commit)
        return doc


DeviceFormSet = forms.formset_factory(form=DeviceForm, formset=BaseDeviceFormSet, extra=1)

