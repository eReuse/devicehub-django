import os
import json
import shutil
import hashlib

from datetime import datetime
from dmidecode import DMIParse
from evidence.xapian import search, index
from evidence.models import Evidence, Annotation
from utils.constants import ALGOS, CHASSIS_DH


def get_mac(hwinfo):

    low_ix = None
    
    nets = [x.split("\n") for x in hwinfo.split("\n\n") 
                if "network interface" in x and "Attached to" in x]
            
    for n in nets:
        ix = None
        if "Attached to:" in n:
            for v in c.split(" "):
                if "#" in v:
                    ix = int(v.strip("#"))
        if not low_ix:
            low_ix = ix
            
        if "HW Address:" in n:
            if low_ix <= ix:
                mac = c.split(" ")[-1]
                return mac
                

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
        if self.json.get("software") == "EreuseWorkbench":
            hid = self.get_hid(self.json)
        else:
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
                owner=self.user.institution,
                type=Annotation.Type.SYSTEM,
                key=k,
                value=v
            )

    def get_chassis_dh(self):
        chassis = self.get_chassis()
        lower_type = chassis.lower()
        for k, v in CHASSIS_DH.items():
            if lower_type in v:
                return k
        return self.default

    def get_sku(self):
        return self.dmi.get("System")[0].get("SKU Number", "n/a").strip()
    
    def get_chassis(self):
        return self.dmi.get("Chassis")[0].get("Type", '_virtual')

    def get_hid(self, snapshot):
        dmidecode_raw = snapshot["data"]["dmidecode"]
        self.dmi = DMIParse(dmidecode_raw)

        manufacturer = self.dmi.manufacturer().strip()
        model = self.dmi.model().strip()
        chassis = self.get_chassis_dh()
        serial_number = self.dmi.serial_number()
        sku = self.get_sku()
        hwinfo_raw = snapshot["data"]["hwinfo"]
        mac = get_mac(hwinfo_raw) or ""

        return f"{manufacturer}{model}{chassis}{serial_number}{sku}{mac}"
