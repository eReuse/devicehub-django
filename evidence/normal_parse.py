import json
import logging

from dmidecode import DMIParse
from django.conf import settings

from evidence import ereuse24
from evidence.mixin_parse import BuildMix
from evidence.normal_parse_details import get_inxi_key, get_inxi, ParseSnapshot
from evidence.universal_parse import get_mac_linux
from utils.constants import ALGO_EREUSE24


logger = logging.getLogger('django')


def get_mac(inxi):
    nets = get_inxi_key(inxi, "Network")
    n_nets = len(nets) - 1

    for i in range(0, n_nets):
        if i + 1 > n_nets:
            break

        n = nets[i]
        iface = nets[i + 1]
        if get_inxi(n, "port"):
            return get_inxi(iface, 'mac')


def clean(msg):
    if not isinstance(msg, str):
        return msg
    return msg.lower().strip().replace(" ", "")


class Build(BuildMix):

    def get_details(self):
        self.from_credential()
        try:
            self.inxi = self.json["data"]["inxi"]
            if isinstance(self.inxi, str):
                self.inxi = json.loads(self.inxi)
        except Exception:
            logger.error("No inxi in snapshot %s", self.uuid)
            self.inxi = None

        dmidecode_raw = self.json["data"].get('dmidecode', '')
        has_dmi = bool(dmidecode_raw)
        if has_dmi:
            dmi = DMIParse(dmidecode_raw)
            chassis = dmi.get('Chassis')
            self.chassis = clean(chassis[0].get('Type', '')) if chassis else ''
            self.manufacturer = clean(dmi.manufacturer())
            self.model = clean(dmi.model())
            self.serial_number = clean(dmi.serial_number())

        if self.inxi and (settings.DEVICEHUB_ALGORITHM_DEVICE == ALGO_EREUSE24 or not has_dmi):
            ereuse24.set_inxi_identity(self, self.inxi)

        self.mac = ""
        net_linux = self.json["data"].get('linux-adapters')
        if net_linux:
            self.mac = get_mac_linux(net_linux) or ""
        if not self.mac and self.inxi:
            self.mac = get_mac(self.inxi) or ""

        if not self.mac:
            txt = "Could not retrieve MAC address in snapshot %s"
            logger.warning(txt, self.uuid)

    def from_credential(self):
        if not self.json.get("credentialSubject"):
            return

        self.uuid = self.json.get("credentialSubject", {}).get("uuid")
        self.json.update(self.json["credentialSubject"])
        if self.json.get("evidence"):
            self.json["data"] = {}
            for ev in self.json["evidence"]:
                k = ev.get("operation")
                if not k:
                    continue
                self.json["data"][k] = ev.get("output")

    def _get_components(self):
        data = ParseSnapshot(self.json)
        self.device = data.device
        self.components = data.components

        self.device.pop("actions", None)
        for c in self.components:
            c.pop("actions", None)
