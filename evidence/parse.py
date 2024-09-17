import os
import json
import shutil
import hashlib

from datetime import datetime
from evidence.xapian import search, index
from evidence.models import Evidence, Annotation
from utils.constants import ALGOS


class Build:
    def __init__(self, evidence_json, user, check=False):
        self.json = evidence_json
        self.uuid = self.json['uuid']
        self.user = user
        self.hid = None
        self.generate_chids()

        if check:
            return

        self.index()
        self.create_annotations()

    def index(self):
        snap = json.dumps(self.json)
        index(self.uuid, snap)

    def generate_chids(self):
        self.algorithms = {
            'hidalgo1': self.get_hid_14(),
        }

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

        for k, v in self.algorithms.items():
            Annotation.objects.create(
                uuid=self.uuid,
                owner=self.user,
                type=Annotation.Type.SYSTEM,
                key=k,
                value=v
            )
