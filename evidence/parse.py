import os
import json
import shutil
import hashlib

from datetime import datetime
from dmidecode import DMIParse
from json_repair import repair_json

from evidence.models import Annotation
from evidence.xapian import index
from utils.constants import ALGOS, CHASSIS_DH


def get_network_cards(child, nets):
    if child['id'] == 'network' and "PCI:" in child.get("businfo"):
        nets.append(child)
    if child.get('children'):
        [get_network_cards(x, nets) for x in child['children']]
        
        
def get_mac(lshw):
    nets = []
    try:
        hw = json.loads(lshw)
    except json.decoder.JSONDecodeError:
        hw = json.loads(repair_json(lshw))
        
    try:
        get_network_cards(hw, nets)
    except Exception as ss:
        print("WARNING!! {}".format(ss))
        return

    nets_sorted = sorted(nets, key=lambda x: x['businfo'])
    # This funcion get the network card integrated in motherboard
    # integrate = [x for x in nets if "pci@0000:00:" in x.get('businfo', '')]

    if nets_sorted:
        return nets_sorted[0]['serial']


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
        index(self.user.institution, self.uuid, snap)

    def generate_chids(self):
        self.algorithms = {
            'hidalgo1': self.get_hid_14(),
        }

    def get_hid_14(self):
        if self.json.get("software") == "workbench-script":
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
                user=self.user,
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

        if not snapshot["data"].get('lshw'):
            return f"{manufacturer}{model}{chassis}{serial_number}{sku}"
        
        lshw = snapshot["data"]["lshw"]
        # mac = get_mac2(hwinfo_raw) or ""
        mac = get_mac(lshw) or ""
        if not mac:
            print(f"WARNING: Could not retrieve MAC address in snapshot {snapshot['uuid']}" )
            # TODO generate system annotation for that snapshot
        else:
            print(f"{manufacturer}{model}{chassis}{serial_number}{sku}{mac}")

        return f"{manufacturer}{model}{chassis}{serial_number}{sku}{mac}"
