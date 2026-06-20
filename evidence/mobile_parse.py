import logging

from evidence.mixin_parse import BuildMix


logger = logging.getLogger('django')


class Build(BuildMix):
    """Parser for snapshots produced by workbench-android.

    Android (non-root) cannot read a stable serial or MAC, so identity comes
    from the operator's manual id, which the app writes into
    ``data.device.serial_number`` (falling back to the per-install UUID). That
    makes the ereuse24 chid unique and human-derived. The ``manual_id`` is also
    carried so a ``custom_id:`` RootAlias can be created (see evidence/parse.py).
    """

    def get_details(self):
        device = self.json.get("data", {}).get("device", {})
        self.device = device
        self.manufacturer = device.get("manufacturer", "")
        self.model = device.get("model", "")
        self.chassis = device.get("chassis", "Handheld")
        self.serial_number = device.get("serial_number", "")
        self.type = device.get("type", "Smartphone")
        self.sku = ""
        self.version = ""
        self.mac = ""
        self.manual_id = device.get("manual_id")

    def _get_components(self):
        from evidence.mobile_parse_details import ParseSnapshot

        data = ParseSnapshot(self.json)
        self.device = data.device
        self.components = data.components
