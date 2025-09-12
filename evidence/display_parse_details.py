import json
import logging



logger = logging.getLogger('django')

class ParseSnapshot:
    def __init__(self, snapshot, default="n/a"):
        self.default = default
        data = snapshot
        if snapshot.get("credentialSubject"):
            data = snapshot["credentialSubject"]

        edid_decode = snapshot.get("data").get("edid_decode", {})
        if not edid_decode:
            self.edid_raw = data.get("data").get("edid_hex", {})

        self.device = {"actions": []}
        self.components = self._parse_edid_decode(edid_decode)
        logger.error(self.components)


        self.snapshot_json = {
            "type": "Snapshot",
            "device": self.device,
            "components": self.components,
            "uuid": data.get("uuid", self.default),
            "endTime": data.get("timestamp", self.default),
            "elapsed": 1,
        }

    def _parse_edid_decode(self, edid_decode_str):
        #TODO: validate this function given other displays
        edid_dict = {}
        current_section = None

        for line in edid_decode_str.splitlines():
            line = line.rstrip()
            if not line:
                continue

            if not line.startswith(" "):
                current_section = line.strip(":")
                edid_dict[current_section] = {}
                continue

            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()
                edid_dict[current_section][key] = value
            else:
                edid_dict[current_section].setdefault("_misc", []).append(line.strip())

        base = edid_dict.get("Block 0, Base EDID", {})
        native = edid_dict.get("Native Video Resolution", {})

        items = [
            {"Manufacturer": base.get("Manufacturer")},
            {"Model": base.get("Model")},
            {"Manufacture Date": base.get("Made in")},
            {"Max Image Size": base.get("Maximum image size")},
            {"Gamma": base.get("Gamma")},
            {"Color Format": base.get("Supported color formats")},
            {"Native Resolution": (native.get("_misc") or [None])[0]},
            {"Preferred Timing": base.get("DTD 1")},
        ]

        return [{k: v} for item in items for k, v in item.items() if v]
