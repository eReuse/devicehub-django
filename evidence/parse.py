import json
import hashlib
import logging

from dmidecode import DMIParse

from evidence.models import SystemProperty
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

        if evidence_json.get("credentialSubject"):
            self.build = normal_parse.Build(evidence_json)
            self.uuid = evidence_json.get("credentialSubject", {}).get("uuid")
        elif evidence_json.get("software") != "workbench-script":
            self.build = old_parse.Build(evidence_json)
        elif evidence_json.get("data",{}).get("lshw"):
            self.build = legacy_parse.Build(evidence_json)
        else:
            self.build = normal_parse.Build(evidence_json)

        if check:
            return

        if not self.build.uuid:
            return

        self.index()
        self.create_annotations()
        if settings.DPP:
            self.register_device_dlt()

    def index(self):
        snap = json.dumps(self.evidence)
        index(self.user.institution, self.uuid, snap)

    def create_annotations(self):
        prop = SystemProperty.objects.filter(
                uuid=self.uuid,
                owner=self.user.institution,
        )

        if prop:
            txt = "Warning: Snapshot %s already registered (annotation exists)"
            logger.warning(txt, self.uuid)
            return

        for k, v in self.build.algorithms.items():
            SystemProperty.objects.create(
                uuid=self.uuid,
                owner=self.user.institution,
                user=self.user,
                key=k,
                value=self.sign(v)
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
