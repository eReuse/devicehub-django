import json
import logging
import re

from evidence.mixin_parse import BuildMix
from evidence.display_parse_details import ParseSnapshot


logger = logging.getLogger('django')

class Build(BuildMix):

    def get_details(self):
        self.from_credential()
        self.type = "Display"
        self._get_components()

        self.manufacturer = self.device.get("manufacturer")
        self.model = self.device.get("model")
        self.serial_number = self.device.get("serialNumber")
        self.version = self.device.get("version")

        if not self.json.get("data", {}).get("edid_decode"):
            logger.error("No 'edid_decode' data found in snapshot %s", self.uuid)

        return


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

        return

    def _get_components(self):
        data = ParseSnapshot(self.json)
        self.device = data.device
        self.components = data.components

        self.device.pop("actions", None)
        for c in self.components:
            c.pop("actions", None)
        return
