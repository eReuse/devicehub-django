import logging

from evidence.mixin_parse import BuildMix


logger = logging.getLogger('django')


class Build(BuildMix):
    # This parse is for get info from snapshots created with old workbench
    # normaly is worbench 11

    def get_details(self):
        device = self.json.get('device', {})
        self.manufacturer = device.get("manufacturer", '')
        self.model = device.get("model", '')
        self.chassis = device.get("chassis", '')
        self.serial_number = device.get("serialNumber", '')
        self.sku = device.get("sku", '')

    def _get_components(self):
        self.components = self.json.get("components", [])
