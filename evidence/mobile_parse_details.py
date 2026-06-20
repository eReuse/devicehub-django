import logging


logger = logging.getLogger('django')


def _gb(num_bytes):
    if not num_bytes:
        return None
    return "{:.0f} GB".format(num_bytes / 1024 ** 3)


def _clean(component):
    """Drop empty values so the dashboard doesn't render blanks."""
    return {k: v for k, v in component.items() if v not in (None, "", [])}


class ParseSnapshot:
    """Builds the device/components view for a workbench-android snapshot.

    Reads ``data.device`` for identity and ``data.android`` for the component
    breakdown (Processor, RamModule, Storage, Display, Battery, Camera). None of
    this affects the ereuse24 chid (which is computed from data.device only).
    """

    def __init__(self, snapshot, default="n/a"):
        self.default = default
        data = snapshot.get("data", {})
        d = data.get("device", {})

        self.device = {
            "type": d.get("type", "Smartphone"),
            "manufacturer": d.get("manufacturer", default),
            "model": d.get("model", default),
            "serialNumber": d.get("serial_number", default),
            "manual_id": d.get("manual_id"),
        }

        self.components = self._build_components(data.get("android", {}))
        self.snapshot_json = {
            "device": self.device,
            "components": self.components,
        }

    def _build_components(self, android):
        components = []

        cpu = android.get("cpu", {})
        if cpu:
            components.append(_clean({
                "type": "Processor",
                "model": cpu.get("soc_model"),
                "cores": cpu.get("cores"),
                "abis": ", ".join(cpu.get("abis", [])),
            }))

        memory = android.get("memory", {})
        if memory.get("total_bytes"):
            components.append(_clean({
                "type": "RamModule",
                "size": _gb(memory.get("total_bytes")),
                "available": _gb(memory.get("available_bytes")),
            }))

        storage = android.get("storage", {})
        if storage.get("total_bytes"):
            components.append(_clean({
                "type": "Storage",
                "size": _gb(storage.get("total_bytes")),
                "free": _gb(storage.get("free_bytes")),
            }))

        display = android.get("display", {})
        if display.get("width_px") or display.get("height_px"):
            components.append(_clean({
                "type": "Display",
                "resolution": "{}x{}".format(
                    display.get("width_px"), display.get("height_px")
                ),
                "density_dpi": display.get("density_dpi"),
            }))

        battery = android.get("battery", {})
        if any(v is not None for v in battery.values()):
            components.append(_clean({
                "type": "Battery",
                "level_percent": battery.get("level_percent"),
                "health_code": battery.get("health_code"),
                "technology": battery.get("technology"),
                "voltage_mv": battery.get("voltage_mv"),
            }))

        for cam in android.get("cameras", []):
            components.append(_clean({
                "type": "Camera",
                "id": cam.get("id"),
                "lens_facing": cam.get("lens_facing"),
                "megapixels": cam.get("megapixels"),
            }))

        return components
