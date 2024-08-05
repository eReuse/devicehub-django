import json
import uuid
import hashlib
import datetime

from django import forms
from evidence.models import Annotation
from evidence.xapian import index

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
    tag = forms.CharField(required=False)
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
        doc = {}
        device = {}
        kv = {}
        self.uuid = str(uuid.uuid4())
        tag = hashlib.sha3_256(self.uuid.encode()).hexdigest()
        for f in self.forms:
            d = f.cleaned_data
            if not d:
                continue
            if d.get("type"):
                device["type"] = d["type"]
            if d.get("amount"):
                device["amount"] = d["amount"]
            if d.get("name"):
                kv[d["name"]] = d.get("value", '')
            if d.get("tag"):
                tag = d["tag"]

        if not device:
            return

        doc["device"] = device

        if kv:
            doc["kv"] = kv

        date = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        
        if doc:
            doc["uuid"] = self.uuid
            doc["endTime"] = date
            doc["software"] = "DeviceHub"
            doc["CUSTOMER_ID"] = tag
            doc["type"] = "WebSnapshot"
        

        if not commit:
            return doc

        self.index(doc)
        self.create_annotations(tag)
        return doc

    def index(self, doc):
        snap = json.dumps(doc)
        index(self.uuid, snap)

    def create_annotations(self, tag):
        Annotation.objects.create(
            uuid=self.uuid,
            owner=self.user,
            type=Annotation.Type.SYSTEM,
            key='CUSTOM_ID',
            value=tag
        )



DeviceFormSet = forms.formset_factory(form=DeviceForm, formset=BaseDeviceFormSet, extra=1)

