#!/usr/bin/env python3
import json
import logging

from evidence.mixin_parse import BuildMix
from evidence.normal_parse_details import ParseSnapshot


logger = logging.getLogger('django')

class Build(BuildMix):

    def get_details(self):
        self.from_credential()
        try:
            if "smartctl" in self.json.get("data", {}) and self.json["data"]["smartctl"]:
                smartctl_str = self.json["data"]["smartctl"][0]

                smartctl_data = json.loads(smartctl_str)

                self.type = "Disk"

                self.manufacturer = smartctl_data.get("model_family")
                self.model = smartctl_data.get("model_name")
                self.serial_number = smartctl_data.get("serial_number")
                self.version = smartctl_data.get("firmware_version")

            else:
                logger.error("No 'smartctl' data found in snapshot %s", self.uuid)

        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
            logger.error("Failed to parse smartctl data for snapshot %s: %s", self.uuid, e)


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
