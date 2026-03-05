import json
import logging
import re

from dmidecode import DMIParse

from utils.constants import CHASSIS_DH, DATASTORAGEINTERFACE


logger = logging.getLogger('django')


INVALID_SERIAL_VALUES = {
    'to be filled by o.e.m.',
    'not specified',
    'not present',
    'n/a',
    '',
}


def clean(value, default=''):
    if not value:
        return default
    return value.strip() if isinstance(value, str) else value


def valid_serial(value):
    if not value:
        return False
    return value.strip().lower() not in INVALID_SERIAL_VALUES


class ParseSnapshot:
    def __init__(self, snapshot, default='n/a'):
        self.default = default
        self.device = {}
        self.components = []

        data = snapshot.get('data', {})
        if snapshot.get('credentialSubject'):
            data = snapshot['credentialSubject'].get('data', data)

        dmidecode_raw = data.get('dmidecode', '')
        for ev in snapshot.get('evidence', []):
            if ev.get('operation') == 'dmidecode':
                dmidecode_raw = ev['output']

        smartctl_raw = data.get('smartctl', [])
        for ev in snapshot.get('evidence', []):
            if ev.get('operation') == 'smartctl':
                smartctl_raw = ev['output']

        # DMIParse expects blocks separated by exactly \n\n.
        # Some generators (dmidecode 3.6 on Windows) produce \n\n\n
        # at the start, which shifts the line index and breaks parsing.
        dmidecode_raw = re.sub(r'\n{3,}', '\n\n', dmidecode_raw)
        self.dmi = DMIParse(dmidecode_raw)
        self.smart = self._loads(smartctl_raw)

        self.set_computer()
        self.set_components()

        self.snapshot_json = {
            'type': 'Snapshot',
            'device': self.device,
            'software': snapshot.get('software', ''),
            'components': self.components,
            'uuid': snapshot.get('uuid', ''),
            'endTime': snapshot.get('timestamp', ''),
            'elapsed': 1,
        }

    # -------------------------------------------------------------------------
    # Device (main machine) — DMI Type 1 + Type 3
    # -------------------------------------------------------------------------

    def set_computer(self):
        self.device['manufacturer'] = clean(self.dmi.manufacturer())
        self.device['model'] = clean(self.dmi.model())
        self.device['serialNumber'] = clean(self.dmi.serial_number())
        self.device['type'] = self._get_type()
        self.device['chassis'] = self._get_chassis_dh()
        self.device['sku'] = clean(self._system().get('SKU Number', ''))
        self.device['version'] = clean(self._system().get('Version', ''))
        self.device['system_uuid'] = clean(self._system().get('UUID', ''))
        self.device['family'] = clean(self._system().get('Family', ''))

    def _system(self):
        systems = self.dmi.get('System')
        return systems[0] if systems else {}

    def _chassis_type(self):
        chassis = self.dmi.get('Chassis')
        return chassis[0].get('Type', '_virtual') if chassis else '_virtual'

    def _get_type(self):
        chassis_type = self._chassis_type().lower()
        CHASSIS_TYPE = {
            'Desktop': ['desktop', 'low-profile', 'tower', 'docking',
                        'all-in-one', 'pizzabox', 'mini-tower', 'space-saving',
                        'lunchbox', 'mini', 'stick'],
            'Laptop':  ['portable', 'laptop', 'convertible', 'tablet',
                        'detachable', 'notebook', 'handheld', 'sub-notebook'],
            'Server':  ['server'],
            'Computer': ['_virtual'],
        }
        for device_type, values in CHASSIS_TYPE.items():
            if chassis_type in values:
                return device_type
        return self.default

    def _get_chassis_dh(self):
        chassis_type = self._chassis_type().lower()
        for k, values in CHASSIS_DH.items():
            if chassis_type in values:
                return k
        return self.default

    # -------------------------------------------------------------------------
    # Components
    # -------------------------------------------------------------------------

    def set_components(self):
        self.get_cpu()
        self.get_ram()
        self.get_mother_board()
        self.get_battery()
        self.get_data_storage()

    # --- Processor (DMI Type 4) ----------------------------------------------

    def get_cpu(self):
        for cpu in self.dmi.get('Processor'):
            serial = cpu.get('Serial Number', '')
            if not valid_serial(serial):
                serial = cpu.get('ID', '').replace(' ', '')

            try:
                cores = int(cpu.get('Core Count', 1))
            except (ValueError, TypeError):
                cores = 1

            try:
                threads = int(cpu.get('Thread Count', 1))
            except (ValueError, TypeError):
                threads = 1

            self.components.append({
                'type': 'Processor',
                'manufacturer': clean(cpu.get('Manufacturer')),
                'model': clean(cpu.get('Version')),
                'brand': clean(cpu.get('Family')),
                'speed': clean(cpu.get('Max Speed')),
                'cores': cores,
                'threads': threads,
                'serialNumber': clean(serial),
                'address': self._get_cpu_address(cpu),
            })

    def _get_cpu_address(self, cpu):
        flags = cpu.get('Flags', [])
        if isinstance(flags, list):
            if any('64-bit' in f for f in flags):
                return 64
        return 32

    # --- RamModule (DMI Type 17) ----------------------------------------------

    def get_ram(self):
        for ram in self.dmi.get('Memory Device'):
            size = ram.get('Size', '')
            if not size or 'no module' in size.lower():
                continue
            speed = ram.get('Speed', '')
            if not speed or speed.lower() in ('unknown', ''):
                continue

            self.components.append({
                'type': 'RamModule',
                'manufacturer': clean(ram.get('Manufacturer', self.default)),
                'model': clean(ram.get('Part Number', self.default)),
                'serialNumber': clean(ram.get('Serial Number', self.default)),
                'size': clean(size),
                'speed': clean(speed),
                'interface': clean(ram.get('Type', 'DDR')),
                'format': clean(ram.get('Form Factor', 'DIMM')),
            })

    # --- Motherboard (DMI Type 2 + Type 0 + Type 8 + Type 16) --------------

    def get_mother_board(self):
        for mb in self.dmi.get('Baseboard'):
            self.components.append({
                'type': 'Motherboard',
                'manufacturer': clean(mb.get('Manufacturer', '')),
                'model': clean(mb.get('Product Name', '')),
                'serialNumber': clean(mb.get('Serial Number', '')),
                'version': clean(mb.get('Version', '')),
                'biosDate': self._get_bios_date(),
                'biosVersion': self._get_bios_revision(),
                'ramMaxSize': self._get_max_ram_size(),
                'ramSlots': len(self.dmi.get('Memory Device')),
                'slots': self._get_ram_slots(),
                'usb': self._count_ports('USB'),
                'serial': self._count_ports('SERIAL'),
                'firewire': self._count_ports('FIRMWARE'),
                'pcmcia': self._count_ports('PCMCIA'),
            })

    def _get_bios_date(self):
        bios = self.dmi.get('BIOS')
        return bios[0].get('Release Date', self.default) if bios else self.default

    def _get_bios_revision(self):
        bios = self.dmi.get('BIOS')
        return bios[0].get('BIOS Revision', '') if bios else ''

    def _get_max_ram_size(self):
        size = 0
        for slot in self.dmi.get('Physical Memory Array'):
            capacity = slot.get('Maximum Capacity', '0').split()[0]
            try:
                size += int(capacity)
            except ValueError:
                pass
        return size

    def _get_ram_slots(self):
        slots = 0
        for array in self.dmi.get('Physical Memory Array'):
            try:
                slots += int(array.get('Number Of Devices', 0))
            except (ValueError, TypeError):
                pass
        return slots

    def _count_ports(self, port_type):
        return len([
            p for p in self.dmi.get('Port Connector')
            if port_type in p.get('Port Type', '').upper()
        ])

    # --- Battery (DMI Type 22) -----------------------------------------------

    def get_battery(self):
        for bat in self.dmi.get('Portable Battery'):
            capacity = bat.get('Design Capacity', '')
            voltage = bat.get('Design Voltage', '')
            serial = bat.get('SBDS Serial Number', '') or bat.get('Serial Number', '')

            # Skip virtual batteries with no real data
            if not capacity or 'unknown' in capacity.lower():
                continue

            self.components.append({
                'type': 'Battery',
                'manufacturer': clean(bat.get('Manufacturer', self.default)),
                'model': clean(bat.get('Name', self.default)),
                'serialNumber': clean(serial),
                'chemistry': clean(bat.get('SBDS Chemistry', self.default)),
                'designCapacity': clean(capacity),
                'designVoltage': clean(voltage),
                'manufactureDate': clean(bat.get('SBDS Manufacture Date', '')),
            })

    # --- Storage (smartctl) --------------------------------------------------

    def get_data_storage(self):
        for sm in self.smart:
            if sm.get('smartctl', {}).get('exit_status') == 1:
                continue

            model_full = sm.get('model_name', '') or ''
            manufacturer = None
            model = model_full
            parts = model_full.split()
            if len(parts) > 1:
                manufacturer = parts[0]
                model = ' '.join(parts[1:])

            self.components.append({
                'type': self._storage_type(sm),
                'manufacturer': manufacturer,
                'model': model,
                'serialNumber': sm.get('serial_number', ''),
                'size': sm.get('user_capacity', {}).get('bytes'),
                'interface': self._storage_interface(sm),
                'firmware': sm.get('firmware_version', ''),
                'hours': sm.get('power_on_time', {}).get('hours', 0),
            })

    def _storage_type(self, sm):
        device_type = sm.get('device', {}).get('type', '')
        if device_type == 'nvme':
            return 'SolidStateDrive'
        rotation = sm.get('rotation_rate', None)
        trim = sm.get('trim', {}).get('supported', False)
        if rotation == 0 or trim:
            return 'SolidStateDrive'
        return 'HardDrive'

    def _storage_interface(self, sm):
        protocol = sm.get('device', {}).get('protocol', 'ATA').upper()
        device_type = sm.get('device', {}).get('type', '').lower()
        if device_type == 'nvme' or protocol == 'NVME':
            return 'NVME'
        if protocol in DATASTORAGEINTERFACE:
            return protocol
        return 'ATA'

    # -------------------------------------------------------------------------
    # Utilities
    # -------------------------------------------------------------------------

    def _loads(self, raw):
        if isinstance(raw, (list, dict)):
            return raw
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except Exception as e:
                logger.warning('universal_parse_details loads error: %s', e)
                return []
        return []
