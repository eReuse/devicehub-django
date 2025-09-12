import json
import logging
import re

from evidence.mixin_parse import BuildMix
from evidence.normal_parse_details import get_inxi_key, get_inxi, ParseSnapshot


logger = logging.getLogger('django')

class Build(BuildMix):

    def get_details(self):

        self.from_credential()
        try:
            self.edid_decode = self.json["data"]["edid_decode"]
            if isinstance(self.edid_decode, str):
                self.edid_decode = json.loads(self.edid_decode)
        except Exception:
            logger.error("No edid-decode in snapshot %s", self.uuid)

        self.type = "Display"

        m = re.search(r"Manufacturer:\s+(\S+)", self.edid_decode)
        if m: self.manufacturer = m.group(1)

        m = re.search(r"Model:\s+(\S+)", self.edid_decode)
        if m: self.model= m.group(1)

        m = re.search(r"Serial Number:\s+(\d+)", self.edid_decode)
        if m: self.serial_number = m.group(1)

        m = re.search(r"EDID Structure Version & Revision:\s+([0-9.]+)", self.edid_decode)
        if m: self.version = m.group(1)


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
