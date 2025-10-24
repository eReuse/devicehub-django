import logging
import pandas as pd

logger = logging.getLogger('django')

MANUFACTURER_CSV_PATH = 'utils/pnp_manufacturer_ids.csv'

class ParseSnapshot:
    def __init__(self, snapshot, default="n/a"):
        self.default = default
        data = snapshot
        if snapshot.get("credentialSubject"):
            data = snapshot["credentialSubject"]

        edid_decode = snapshot.get("data").get("edid_decode", {})
        if not edid_decode:
            self.edid_raw = data.get("data").get("edid_hex", {})

        info = self._parse_edid_decode(edid_decode)

        self.device = {
            "actions": [],
            "manufacturer_id": info.get("Manufacturer ID"),
            "manufacturer": info.get("Manufacturer"),
            "model": info.get("Model"),
            "serialNumber": info.get("Serial Number"),
            "edid_version": info.get("EDID Version"),
        }

        #done this way so it rendes properly on components tab
        self.components = [{k: v} for k, v in info.items() if v is not None]

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

        manufacturer_map = {}
        try:
            manufacturer_df = pd.read_csv(MANUFACTURER_CSV_PATH)
            manufacturer_map = manufacturer_df.set_index('PNP ID')['Company'].to_dict()
        except FileNotFoundError:
            logger.warning(f"Manufacturer mapping file not found at {MANUFACTURER_CSV_PATH}. Using raw IDs.")
        except Exception as e:
            logger.error(f"Error loading manufacturer mapping CSV: {e}")

        man_string = manufacturer_map.get(base.get("Manufacturer",""))

        info = {
            "Manufacturer": man_string,
            "Manufacturer ID": base.get("Manufacturer"),
            "EDID Version": base.get("EDID Structure Version & Revision"),
            "Serial Number": base.get("Serial Number"),
            "Model": base.get("Model"),
            "Manufacture Date": base.get("Made in"),
            "Max Image Size": base.get("Maximum image size"),
            "Gamma": base.get("Gamma"),
            "Color Format": base.get("Supported color formats"),
            "Native Resolution": (native.get("_misc") or [None])[0],
            "Preferred Timing": base.get("DTD 1"),
            "Device Type": "Display",
        }

        misc = base.get("_misc")
        if misc:
            info["Misc"] = "\n  - " + "\n  - ".join(misc)

        return info
