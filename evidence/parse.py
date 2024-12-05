import json
import hashlib
import logging

from dmidecode import DMIParse

from evidence.models import Annotation
from evidence.xapian import index
from utils.constants import CHASSIS_DH
from evidence.parse_details import get_inxi_key, get_inxi

logger = logging.getLogger('django')


def get_mac(inxi):
    nets = get_inxi_key(inxi, "Network")
    networks = [(nets[i], nets[i + 1]) for i in range(0, len(nets) - 1, 2)]

    for n, iface in networks:
        if get_inxi(n, "port"):
            return get_inxi(iface, 'mac')


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
        annotation = Annotation.objects.filter(
                uuid=self.uuid,
                owner=self.user.institution,
                type=Annotation.Type.SYSTEM,
        )

        if annotation:
            txt = "Warning: Snapshot %s already registered (annotation exists)"
            logger.warning(txt, self.uuid)
            return

        for k, v in self.algorithms.items():
            Annotation.objects.create(
                uuid=self.uuid,
                owner=self.user.institution,
                user=self.user,
                type=Annotation.Type.SYSTEM,
                key=k,
                value=v
            )

    def get_hid(self, snapshot):
        try:
            self.inxi = json.loads(self.json["data"]["inxi"])
        except Exception:
            logger.error("No inxi in snapshot %s", self.uuid)
            return ""
        
        machine = get_inxi_key(self.inxi, 'Machine')
        for m in machine:
            system = get_inxi(m, "System")
            if system:
                manufacturer = system
                model = get_inxi(m, "product")
                serial_number = get_inxi(m, "serial")
                chassis = get_inxi(m, "Type")
            else:
                sku = get_inxi(m, "part-nu")

        mac = get_mac(self.inxi) or ""
        if not mac:
            txt = "Could not retrieve MAC address in snapshot %s"
            logger.warning(txt, snapshot['uuid'])
            return f"{manufacturer}{model}{chassis}{serial_number}{sku}"

        return f"{manufacturer}{model}{chassis}{serial_number}{sku}{mac}"
