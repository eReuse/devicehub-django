import logging

from dmidecode import DMIParse

from evidence.normal_parse_details import get_inxi_key, get_inxi


logger = logging.getLogger('django')


def clean(value):
    if not isinstance(value, str):
        return value
    return value.lower().strip().replace(" ", "")


def _from_dmidecode(sources):
    raw = sources.dmidecode
    if not raw:
        return None
    dmi = DMIParse(raw)
    return {
        "manufacturer": dmi.manufacturer(),
        "model": dmi.model(),
        "serial_number": dmi.serial_number(),
    }


def _from_native(native_device):
    if not native_device:
        return None
    return {
        "manufacturer": native_device.get("manufacturer"),
        "model": native_device.get("model"),
        "serial_number": (
            native_device.get("serialNumber")
            or native_device.get("serial_number")
        ),
    }


def _from_inxi(sources):
    inxi = sources.inxi
    if not inxi:
        return None
    machine = get_inxi_key(inxi, "Machine") or []
    for m in machine:
        system = get_inxi(m, "System")
        if system:
            return {
                "manufacturer": system,
                "model": get_inxi(m, "product"),
                "serial_number": get_inxi(m, "serial"),
            }
    return None


def parse_identity(sources, native_device=None):
    """Resolve device identity for the ereuse26 algorithm, dmidecode-first.

    EREUSE26 = manufacturer + model + serial_number + mac (no chassis), so this
    only resolves the first three fields; the mac stays as each parser computed
    it. dmidecode is the primary source; the native 'device' dict (wb11/web) and
    inxi are fallbacks, so every snapshot format yields a consistent, normalized
    identity.
    """
    identity = (
        _from_dmidecode(sources)
        or _from_native(native_device)
        or _from_inxi(sources)
        or {}
    )
    return {k: clean(v) for k, v in identity.items()}
