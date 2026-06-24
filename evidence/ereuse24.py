"""Identity override for the legacy ereuse24 algorithm.

ereuse24 derives the device identity (and chassis) from inxi's Machine/System
block instead of dmidecode. Kept isolated in its own module so the whole branch
can be removed once ereuse26 fully replaces ereuse24: delete this file and the
single call site in normal_parse.Build.get_details.
"""
from evidence.normal_parse_details import get_inxi


def set_inxi_identity(build, machine_entry, system):
    build.manufacturer = system
    build.type = get_inxi(machine_entry, "Type")
    build.model = get_inxi(machine_entry, "product")
    build.serial_number = get_inxi(machine_entry, "serial")
    build.chassis = build.type
