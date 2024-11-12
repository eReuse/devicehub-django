import json
import hashlib
import logging

from dmidecode import DMIParse
from evidence.parse_details import ParseSnapshot

from evidence.models import SystemProperty
from evidence.xapian import index
from evidence.parse_details import get_inxi_key, get_inxi
from django.conf import settings

if settings.DPP:
    from dpp.api_dlt import register_device_dlt, register_passport_dlt

logger = logging.getLogger('django')


def get_mac(inxi):
    nets = get_inxi_key(inxi, "Network")
    networks = [(nets[i], nets[i + 1]) for i in range(0, len(nets) - 1, 2)]

    for n, iface in networks:
        if get_inxi(n, "port"):
            return get_inxi(iface, 'mac')


class Build:
    def __init__(self, evidence_json, user, check=False):
        self.evidence = evidence_json.copy()
        self.json = evidence_json.copy()

        if evidence_json.get("credentialSubject"):
            self.json.update(evidence_json["credentialSubject"])
        if evidence_json.get("evidence"):
            self.json["data"] = {}
            for ev in evidence_json["evidence"]:
                k = ev.get("operation")
                if not k:
                    continue
                self.json["data"][k] = ev.get("output")

        self.uuid = self.json['uuid']
        self.user = user
        self.hid = None
        self.chid = None
        self.phid = self.get_signature(self.json)
        self.generate_chids()

        if check:
            return

        self.index()
        self.create_properties()
        if settings.DPP:
            self.register_device_dlt()

    def index(self):
        snap = json.dumps(self.evidence)
        index(self.user.institution, self.uuid, snap)

    def generate_chids(self):
        self.algorithms = {
            'hidalgo1': self.get_hid_14(),
            'legacy_dpp': self.get_chid_dpp(),
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

        self.chid = hashlib.sha3_256(hid.encode()).hexdigest()
        return self.chid

    def get_chid_dpp(self):
        if self.json.get("software") == "workbench-script":
            device = ParseSnapshot(self.json).device
        else:
            device = self.json['device']

        hid = self.get_id_hw_dpp(device)
        self.chid = hashlib.sha3_256(hid.encode("utf-8")).hexdigest()
        return self.chid

    def get_id_hw_dpp(self, d):
        manufacturer = d.get("manufacturer", '')
        model = d.get("model", '')
        chassis = d.get("chassis", '')
        serial_number = d.get("serialNumber", '')
        sku = d.get("sku", '')
        typ = d.get("type", '')
        version = d.get("version", '')

        return f"{manufacturer}{model}{chassis}{serial_number}{sku}{typ}{version}"

    def get_phid(self):
        if self.json.get("software") == "workbench-script":
            data = ParseSnapshot(self.json)
            self.device = data.device
            self.components = data.components
        else:
            self.device = self.json.get("device")
            self.components = self.json.get("components", [])

        self.device.pop("actions", None)
        for c in self.components:
            c.pop("actions", None)

        device = self.get_id_hw_dpp(self.device)
        components = sorted(self.components, key=lambda x: x.get("type"))
        doc = [("computer", device)]

        for c in components:
            doc.append((c.get("type"), self.get_id_hw_dpp(c)))

        return doc

    def create_properties(self):
        property = SystemProperty.objects.filter(
                uuid=self.uuid,
                owner=self.user.institution,
                type=Property.Type.SYSTEM,
        )

        if property:
            txt = "Warning: Snapshot %s already registered (property exists)"
            logger.warning(txt, self.uuid)
            return

        for k, v in self.algorithms.items():
            SystemProperty.objects.create(
                uuid=self.uuid,
                owner=self.user.institution,
                user=self.user,
                type=Property.Type.SYSTEM,
                key=k,
                value=v
            )

    def get_hid(self, snapshot):
        try:
            self.inxi = self.json["data"]["inxi"]
            if isinstance(self.inxi, str):
                self.inxi = json.loads(self.inxi)
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

    def get_signature(self, doc):
        return hashlib.sha3_256(json.dumps(doc).encode()).hexdigest()

    def register_device_dlt(self):
        chid = self.algorithms.get('legacy_dpp')
        phid = self.get_signature(self.get_phid())
        register_device_dlt(chid, phid, self.uuid, self.user)
        register_passport_dlt(chid, phid, self.uuid, self.user)
