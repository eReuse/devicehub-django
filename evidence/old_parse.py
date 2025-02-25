import logging

from evidence.mixin_parse import BuildMix


logger = logging.getLogger('django')


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

    def _get_components(self):
        self.components = self.json.get("components", [])

        self.device.pop("actions", None)
        for c in self.components:
            c.pop("actions", None)
