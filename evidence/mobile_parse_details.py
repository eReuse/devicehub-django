import logging
from collections import Counter


logger = logging.getLogger('django')


BATTERY_HEALTH = {
    1: "Unknown",
    2: "Good",
    3: "Overheat",
    4: "Dead",
    5: "Over voltage",
    6: "Unspecified failure",
    7: "Cold",
}


def _gb(num_bytes):
    if not num_bytes:
        return None
    return "{:.0f} GB".format(num_bytes / 1024 ** 3)


def _clean(component):
    """Drop empty values so the dashboard doesn't render blanks."""
    return {k: v for k, v in component.items() if v not in (None, "", [])}


def _known(value):
    """Discard Android placeholders that are not useful inventory values."""
    if value is None or str(value).strip().lower() in ("", "unknown", "n/a"):
        return None
    return value


def _cpu_frequencies(raw):
    """Present per-core maximum frequencies as a compact inventory value."""
    if not raw:
        return None
    values = raw if isinstance(raw, list) else str(raw).split(",")
    try:
        frequencies = [int(value) for value in values if str(value).strip()]
    except (TypeError, ValueError):
        return None

    counts = Counter(frequencies)
    formatted = []
    for frequency, count in sorted(counts.items()):
        ghz = "{:.2f}".format(frequency / 1_000_000).rstrip("0").rstrip(".")
        formatted.append("{} x {} GHz".format(count, ghz))
    return ", ".join(formatted)


def _number(value, digits=1):
    """Round noisy Android floats and return whole values as integers."""
    if value is None:
        return None
    try:
        rounded = round(float(value), digits)
    except (TypeError, ValueError):
        return value
    return int(rounded) if rounded.is_integer() else rounded


def _battery_health(value):
    try:
        return BATTERY_HEALTH.get(int(value))
    except (TypeError, ValueError):
        return None


class ParseSnapshot:
    """Builds the device/components view for a workbench-android snapshot.

    Reads ``data.device`` for identity and the Android, signals, usage and
    whitelisted system-property blocks for the component breakdown. None of
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

        self.components = self._build_components(data)
        self.snapshot_json = {
            "device": self.device,
            "components": self.components,
        }

    def _build_components(self, data):
        components = []
        android = data.get("android", {})
        signals = data.get("signals", {})
        usage = data.get("usage", {})
        properties = data.get("system_properties", {})

        board_model = (
            _known(properties.get("ro.board.boardname"))
            or _known(signals.get("board"))
        )
        board_platform = (
            _known(signals.get("hardware"))
            or _known(properties.get("ro.board.platform"))
            or _known(properties.get("ro.product.platform"))
        )
        board_version = _known(properties.get("ro.product.hardwareversion"))
        if board_model or board_platform or board_version:
            components.append(_clean({
                "type": "Motherboard",
                "manufacturer": android.get("manufacturer"),
                "model": board_model,
                "platform": board_platform,
                "version": board_version,
            }))

        cpu = android.get("cpu", {})
        if cpu:
            abis = cpu.get("abis", [])
            cpu_model = (
                _known(cpu.get("soc_model"))
                or _known(properties.get("ro.config.cpu_info_display"))
                or _known(properties.get("ro.soc.model"))
                or board_platform
            )
            components.append(_clean({
                "type": "Processor",
                "manufacturer": _known(properties.get("ro.soc.manufacturer")),
                "model": cpu_model,
                "cores": cpu.get("cores"),
                "bits": (
                    64 if any("64" in abi for abi in abis) else 32
                ) if abis else None,
                "abis": ", ".join(abis),
                "max_frequency": _cpu_frequencies(signals.get("cpu_max_freq_khz")),
            }))

        memory = android.get("memory", {})
        if memory.get("total_bytes"):
            components.append(_clean({
                "type": "RamModule",
                "size": _gb(memory.get("total_bytes")),
                "interface": "Integrated",
            }))

        storage = android.get("storage", {})
        if storage.get("total_bytes"):
            components.append(_clean({
                "type": "Storage",
                "partition": "Android data",
                "size": _gb(storage.get("total_bytes")),
                "interface": "Integrated",
            }))

        display = android.get("display", {})
        if display.get("width_px") or display.get("height_px"):
            components.append(_clean({
                "type": "Display",
                "resolution": "{}x{}".format(
                    display.get("width_px"), display.get("height_px")
                ),
                "density_dpi": display.get("density_dpi"),
                "xdpi": _number(signals.get("display_xdpi")),
                "ydpi": _number(signals.get("display_ydpi")),
                "refresh_rate_hz": _number(signals.get("display_refresh_rate_hz")),
            }))

        battery = android.get("battery", {})
        if any(v is not None for v in battery.values()):
            health_code = battery.get("health_code") or signals.get("battery_health_code")
            components.append(_clean({
                "type": "Battery",
                "condition": _battery_health(health_code),
                "health_percent": _number(usage.get("battery_health_percent")),
                "design_capacity_mah": _number(signals.get("battery_design_capacity_mah")),
                "cycles": usage.get("battery_cycle_count"),
                "technology": battery.get("technology"),
            }))

        for cam in android.get("cameras", []):
            components.append(_clean({
                "type": "Camera",
                "id": cam.get("id"),
                "lens_facing": cam.get("lens_facing"),
                "megapixels": _number(cam.get("megapixels")),
            }))

        return components
