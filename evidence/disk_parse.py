#!/usr/bin/env python3
import json
import logging

from evidence.mixin_parse import BuildMix
from evidence.disk_parse_details import ParseSnapshot


logger = logging.getLogger('django')

class Build(BuildMix):
    def get_details(self):
        self.from_credential()
        try:
            smartctl_data = self.json.get("data", {}).get("smartctl")

            if not smartctl_data:
                logger.error("No 'smartctl' data found in snapshot %s", self.uuid)
                return

            if isinstance(smartctl_data, list) and smartctl_data:
                smartctl_data = smartctl_data[0]

            if isinstance(smartctl_data, str):
                try:
                    smartctl_data = json.loads(smartctl_data)
                except json.JSONDecodeError as e:
                    logger.error("Could not decode smartctl JSON string for %s: %s", self.uuid, e)
                    return

            if not isinstance(smartctl_data, dict):
                logger.error("'smartctl' data is not a dictionary for snapshot %s. Type: %s", self.uuid, type(smartctl_data))
                return

            self.type = "Disk"
            self.manufacturer = smartctl_data.get("model_family")
            self.model = smartctl_data.get("model_name")
            self.serial_number = smartctl_data.get("serial_number")
            self.version = smartctl_data.get("firmware_version")

        except Exception as e:
            logger.error("An unexpected error occurred parsing smartctl data for %s: %s", self.uuid, e, exc_info=True)

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
