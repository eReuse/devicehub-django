"""Identity override for the legacy ereuse24 algorithm.

ereuse24 derives the device identity (and chassis) from inxi's Machine/System
block instead of dmidecode. Kept isolated in its own module so the whole branch
can be removed once ereuse26 fully replaces ereuse24: delete this file and the
single call site in normal_parse.Build.get_details.
"""
from evidence.normal_parse_details import get_inxi_key, get_inxi


def set_inxi_identity(build, inxi):
    machine = get_inxi_key(inxi, 'Machine')
    build.type = ""
    for m in machine:
        system = get_inxi(m, "System")
        if system:
            build.manufacturer = system
            build.model = get_inxi(m, "product")
            build.serial_number = get_inxi(m, "serial")
            build.version = get_inxi(m, "v")
        else:
            build.manufacturer = build.manufacturer or get_inxi(m, "Mobo")
            build.model = build.model or get_inxi(m, "model")
            build.serial_number = build.serial_number or get_inxi(m, "serial")
            build.system_uuid = get_inxi(m, "uuid")
            build.sku = get_inxi(m, "part-nu")

        build.type = build.type or get_inxi(m, "Type")
        build.chassis = build.type
