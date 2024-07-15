import os
import json
import shutil
import xapian
import hashlib

from datetime import datetime
from snapshot.models import Snapshot, Annotation
from snapshot.xapian import search, indexer, database


HID_ALGO1 = [
    "manufacturer",
    "model",
    "chassis",
    "serialNumber",
    "sku"
]


class Build:
    def __init__(self, snapshot_json, user):
        self.json = snapshot_json
        self.user = user
        self.hid = None

        self.index()
        self.create_annotation()

    def index(self):
        matches = search(self.json['uuid'], limit=1)
        if matches.size() > 0:
            return

        snap = json.dumps(self.json)
        doc = xapian.Document()
        doc.set_data(snap)

        indexer.set_document(doc)
        indexer.index_text(snap)

        # Add the document to the database.
        database.add_document(doc)

    def get_hid_14(self):
        device = self.json['device']
        manufacturer = device.get("manufacturer", '')
        model = device.get("model", '')
        chassis = device.get("chassis", '')
        serial_number = device.get("serialNumber", '')
        sku = device.get("sku", '')
        hid = f"{manufacturer}{model}{chassis}{serial_number}{sku}"
        return hashlib.sha3_256(hid.encode()).hexdigest()

    def create_annotation(self):
        uuid = self.json['uuid']
        owner = self.user
        key = 'hidalgo1'
        value = self.get_hid_14()
        Annotation.objects.create(
            uuid=uuid,
            owner=owner,
            key=key,
            value=value
        )

