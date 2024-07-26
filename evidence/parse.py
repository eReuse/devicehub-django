import os
import json
import shutil
import hashlib

from datetime import datetime
from evidence.xapian import search, index
from evidence.models import Evidence, Annotation
from utils.constants import ALGOS


class Build:
    def __init__(self, evidence_json, user):
        self.json = evidence_json
        self.uuid = self.json['uuid']
        self.user = user
        self.hid = None

        self.index()
        self.create_annotations()

    def index(self):
        snap = json.dumps(self.json)
        index(self.uuid, snap)

    def get_hid_14(self):
        device = self.json['device']
        manufacturer = device.get("manufacturer", '')
        model = device.get("model", '')
        chassis = device.get("chassis", '')
        serial_number = device.get("serialNumber", '')
        sku = device.get("sku", '')
        hid = f"{manufacturer}{model}{chassis}{serial_number}{sku}"
        return hashlib.sha3_256(hid.encode()).hexdigest()

    def create_annotations(self):
        algorithms = {
            'hidalgo1': self.get_hid_14(),
        }

        # TODO is neccesary?
        annotation = Annotation.objects.filter(
            owner=self.user,
            type=Annotation.Type.SYSTEM,
            key='hidalgo1',
            value = algorithms['hidalgo1']
        ).first()

        for k, v in algorithms.items():
            if annotation and k == annotation.key:
                continue
        
            Annotation.objects.create(
                uuid=self.uuid,
                owner=self.user,
                type=Annotation.Type.SYSTEM,
                key=k,
                value=v
            )

