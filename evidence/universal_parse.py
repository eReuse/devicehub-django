import json
import logging
import re

from dmidecode import DMIParse
from evidence.mixin_parse import BuildMix
from evidence.universal_parse_details import ParseSnapshot


logger = logging.getLogger('django')


def _parse_pci_location(pnp_device_id):
    """
    Extracts (bus, device, function) from a Windows PnPDeviceID.
    Returns None if the instance ID format is not decodeable.

    Windows encodes the PCI location in the last segment of the path:
      PCI\\VEN_XXXX&DEV_XXXX&...\\3&b1bfb68&0&C8
    The trailing hex value packs:  (bus << 8) | (device << 3) | function
    Devices whose path ends in a long alphanumeric ID (e.g. WiFi Mini-PCIe)
    do not follow this format and are skipped.
    """
    parts = pnp_device_id.replace('\\\\', '\\').split('\\')
    if len(parts) < 3:
        return None

    instance_id = parts[-1]
    match = re.match(r'^\d+&[0-9a-fA-F]+&\d+&([0-9a-fA-F]+)$', instance_id)
    if not match:
        return None

    code = int(match.group(1), 16)
    return (code >> 8, (code >> 3) & 0x1F, code & 0x07)


def get_mac_win(net_adapters):
    """
    Returns the MAC address of the most integrated (lowest PCI bus/device/function)
    network adapter from a Get-NetAdapter | ConvertTo-Json list.

    Prefers PermanentAddress (no separators) and falls back to MacAddress.
    Returns None if no adapter with a decodeable PCI location is found.
    """
    if not net_adapters or not isinstance(net_adapters, list):
        return None

    best_mac = None
    best_location = None

    for adapter in net_adapters:
        pnp_id = adapter.get('PnPDeviceID', '')
        if not pnp_id:
            continue

        location = _parse_pci_location(pnp_id)
        if location is None:
            continue

        raw = adapter.get('PermanentAddress') or adapter.get('MacAddress', '')
        if not raw:
            continue

        if best_location is None or location < best_location:
            best_location = location
            best_mac = _normalize_mac(raw)

    return best_mac


def _normalize_mac(raw):
    """Normalizes a MAC to lowercase colon-separated format (aa:bb:cc:dd:ee:ff)."""
    digits = re.sub(r'[^0-9a-fA-F]', '', raw)
    return ':'.join(digits[i:i+2] for i in range(0, 12, 2)).lower()


def _parse_pci_bdf(bdf):
    """
    Extracts (domain, bus, device, function) from a Linux PCI address.
    Returns None when the string is not a PCI BDF (e.g. loopback, USB or
    virtual interfaces), so callers skip non-PCI interfaces the same way
    inxi's "port" filter does.

    sysfs exposes the address as DOMAIN:BUS:DEVICE.FUNCTION, e.g.
      0000:00:1f.6
    """
    match = re.match(
        r'^([0-9a-fA-F]{4}):([0-9a-fA-F]{2}):([0-9a-fA-F]{2})\.([0-9a-fA-F])$',
        bdf.strip(),
    )
    if not match:
        return None
    return tuple(int(g, 16) for g in match.groups())


def get_mac_linux(net_sysfs):
    """
    Returns the MAC of the most integrated (lowest PCI domain/bus/device/function)
    network interface from a minimal /sys/class/net dump.

    Linux mirror of get_mac_win for snapshots that ship a sysfs listing
    instead of inxi. Each line is "BDF iface MAC", e.g.:
      0000:00:1f.6 enp0s31f6 54:e1:ad:11:fb:b7
    Non-PCI interfaces (loopback, USB, virtual) lack a decodeable BDF and are
    skipped, so the result is the lowest-bus PCI card just like the inxi path.
    Returns None if no PCI interface with a valid MAC is found.
    """
    if isinstance(net_sysfs, str):
        lines = net_sysfs.splitlines()
    elif isinstance(net_sysfs, list):
        lines = net_sysfs
    else:
        return None

    best_mac = None
    best_location = None

    for line in lines:
        parts = line.split()
        if len(parts) < 3:
            continue
        bdf, _iface, raw = parts[0], parts[1], parts[2]

        location = _parse_pci_bdf(bdf)
        if location is None:
            continue

        mac = _normalize_mac(raw)
        if mac in ('', '00:00:00:00:00:00', 'ff:ff:ff:ff:ff:ff'):
            continue

        if best_location is None or location < best_location:
            best_location = location
            best_mac = mac

    return best_mac


class Build(BuildMix):
    """
    Universal parser that uses only dmidecode + smartctl.
    Does not require inxi, lshw or hwinfo.
    Suitable for snapshots from Windows/macOS environments or
    any snapshot that only includes these two data sources.
    """

    def get_details(self):
        data = self.json.get('data', {})

        dmidecode_raw = data.get('dmidecode', '')

        if not dmidecode_raw:
            txt = 'universal_parse: snapshot %s has no dmidecode data'
            logger.error(txt, self.uuid)
            return

        dmi = DMIParse(dmidecode_raw)

        self.manufacturer = dmi.manufacturer().strip()
        self.model = dmi.model().strip()
        self.serial_number = dmi.serial_number().strip()

        chassis = dmi.get('Chassis')
        self.chassis = chassis[0].get('Type', '').lower() if chassis else ''

        system = dmi.get('System')
        if system:
            self.sku = system[0].get('SKU Number', '').strip()
            self.version = system[0].get('Version', '').strip()

        net_win = data.get('get-netadapter')
        net_linux = data.get('linux-adapters')

        if isinstance(net_win, str):
            try:
                net_win = json.loads(net_win)
            except Exception:
                net_win = []

        self.mac = ''
        if net_win:
            self.mac = get_mac_win(net_win) or ''
        elif net_linux:
            self.mac = get_mac_linux(net_linux) or ''

        if not self.mac:
            logger.warning(
                'universal_parse: no MAC in snapshot %s',
                self.uuid,
            )

    def _get_components(self):
        data = ParseSnapshot(self.json)
        self.device = data.device
        self.components = data.components

        self.device.pop('actions', None)
        for c in self.components:
            c.pop('actions', None)
