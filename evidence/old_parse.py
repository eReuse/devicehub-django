import logging

from evidence.mixin_parse import BuildMix
from evidence.legacy_parse import get_mac

logger = logging.getLogger('django')

# Permanent HW Address
# [x for x in ev.doc["debug"]["hwinfo"].split("\n\n") if "HW Address" in x]

class Build(BuildMix):
    # This parse is for get info from snapshots created with old workbench
    # normaly is worbench 11

    def get_details(self):
        self.device = self.json.get('device', {})
        self.manufacturer = self.device.get("manufacturer", '')
        self.model = self.device.get("model", '')
        self.chassis = self.device.get("chassis", '')
        self.serial_number = self.device.get("serialNumber", '')
        self.sku = self.device.get("sku", '')
        self.type = self.device.get("type", '')
        self.version = self.device.get("version", '')

        self.mac = self.get_mac()
        if not self.mac:
            txt = "Could not retrieve MAC address in snapshot %s"
            logger.warning(txt, self.uuid)

    def _get_components(self):
        self.components = self.json.get("components", [])

        self.device.pop("actions", None)
        for c in self.components:
            c.pop("actions", None)

    def get_mac(self):
        lshw = self.json.get("debug", {}).get("lshw")
        if lshw:
            a = get_mac(lshw) or ""
            if not a:
                get_mac(lshw)
            return get_mac(lshw) or ""
        return ""
