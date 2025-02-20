import json
import logging

from dmidecode import DMIParse


logger = logging.getLogger('django')


def get_inxi_key(inxi, component):
    for n in inxi:
        for k, v in n.items():
            if component in k:
                return v


def get_inxi(n, name):
    for k, v in n.items():
        if f"#{name}" in k:
            return v

    return ""


class ParseSnapshot:
    def __init__(self, snapshot, default="n/a"):
        self.default = default
        self.dmidecode_raw = snapshot.get("data", {}).get("dmidecode", "{}")
        self.smart_raw = snapshot.get("data", {}).get("smartctl", [])
        self.inxi_raw = snapshot.get("data", {}).get("inxi", "") or ""
        for ev in snapshot.get("evidence", []):
            if "dmidecode" == ev.get("operation"):
                self.dmidecode_raw = ev["output"]
            if "inxi" == ev.get("operation"):
                self.inxi_raw = ev["output"]
            if "smartctl" == ev.get("operation"):
                self.smart_raw = ev["output"]
        data = snapshot
        if snapshot.get("credentialSubject"):
            data = snapshot["credentialSubject"]

        self.device = {"actions": []}
        self.components = []

        self.dmi = DMIParse(self.dmidecode_raw)
        self.smart = self.loads(self.smart_raw)
        self.inxi = self.loads(self.inxi_raw)

        self.set_computer()
        self.set_components()
        self.snapshot_json = {
            "type": "Snapshot",
            "device": self.device,
            "software": data["software"],
            "components": self.components,
            "uuid": data['uuid'],
            "endTime": data["timestamp"],
            "elapsed": 1,
        }

    def set_computer(self):
        machine = get_inxi_key(self.inxi, 'Machine') or []
        for m in machine:
            system = get_inxi(m, "System")
            if system:
                self.device['manufacturer'] = system
                self.device['model'] = get_inxi(m, "product")
                self.device['serialNumber'] = get_inxi(m, "serial")
                self.device['type'] = get_inxi(m, "Type")
                self.device['chassis'] = self.device['type']
                self.device['version'] = get_inxi(m, "v")
            else:
                self.device['system_uuid'] = get_inxi(m, "uuid")
                self.device['sku'] = get_inxi(m, "part-nu")

    def set_components(self):
        self.get_mother_board()
        self.get_cpu()
        self.get_ram()
        self.get_graphic()
        self.get_display()
        self.get_networks()
        self.get_sound_card()
        self.get_data_storage()
        self.get_battery()

    def get_mother_board(self):
        machine = get_inxi_key(self.inxi, 'Machine') or []
        mb = {"type": "Motherboard",}
        for m in machine:
            bios_date = get_inxi(m, "date")
            if not bios_date:
                continue
            mb["manufacturer"] = get_inxi(m, "Mobo")
            mb["model"] = get_inxi(m, "model")
            mb["serialNumber"] = get_inxi(m, "serial")
            mb["version"] = get_inxi(m, "v")
            mb["biosDate"] = bios_date
            mb["biosVersion"] = self.get_bios_version()
            mb["firewire"]: self.get_firmware_num()
            mb["pcmcia"]: self.get_pcmcia_num()
            mb["serial"]: self.get_serial_num()
            mb["usb"]: self.get_usb_num()

            self.get_ram_slots(mb)

        self.components.append(mb)

    def get_ram_slots(self, mb):
        memory = get_inxi_key(self.inxi, 'Memory') or []
        for m in memory:
            slots = get_inxi(m, "slots")
            if not slots:
                continue
            mb["slots"] = slots
            mb["ramSlots"] = get_inxi(m, "modules")
            mb["ramMaxSize"] = get_inxi(m, "capacity")


    def get_cpu(self):
        cpu = get_inxi_key(self.inxi, 'CPU') or []
        cp = {"type": "Processor"}
        vulnerabilities = []
        for c in cpu:
            base = get_inxi(c, "model")
            if base:
                cp["model"] = get_inxi(c, "model")
                cp["arch"] = get_inxi(c, "arch")
                cp["bits"] = get_inxi(c, "bits")
                cp["gen"] = get_inxi(c, "gen")
                cp["family"] = get_inxi(c, "family")
                cp["date"] = get_inxi(c, "built")
                continue
            des = get_inxi(c, "L1")
            if des:
                cp["L1"] = des
                cp["L2"] = get_inxi(c, "L2")
                cp["L3"] = get_inxi(c, "L3")
                cp["cpus"] = get_inxi(c, "cpus")
                cp["cores"] = get_inxi(c, "cores")
                cp["threads"] = get_inxi(c, "threads")
                continue
            bogo = get_inxi(c, "bogomips")
            if bogo:
                cp["bogomips"] = bogo
                cp["base/boost"] = get_inxi(c, "base/boost")
                cp["min/max"] = get_inxi(c, "min/max")
                cp["ext-clock"] = get_inxi(c, "ext-clock")
                cp["volts"] = get_inxi(c, "volts")
                continue
            ctype = get_inxi(c, "Type")
            if ctype:
                v = {"Type": ctype}
                status = get_inxi(c, "status")
                if status:
                    v["status"] = status
                mitigation = get_inxi(c, "mitigation")
                if mitigation:
                    v["mitigation"] = mitigation
                vulnerabilities.append(v)

        self.components.append(cp)


    def get_ram(self):
        memory = get_inxi_key(self.inxi, 'Memory') or []
        mem = {"type": "RamModule"}

        for m in memory:
            base = get_inxi(m, "System RAM")
            if base:
                mem["size"] = get_inxi(m, "total")
            slot = get_inxi(m, "manufacturer")
            if slot:
                mem["manufacturer"] = slot
                mem["model"] = get_inxi(m, "part-no")
                mem["serialNumber"] = get_inxi(m, "serial")
                mem["speed"] = get_inxi(m, "speed")
                mem["bits"] = get_inxi(m, "data")
                mem["interface"] = get_inxi(m, "type")
            module = get_inxi(m, "modules")
            if module:
                mem["modules"] = module

        self.components.append(mem)

    def get_graphic(self):
        graphics = get_inxi_key(self.inxi, 'Graphics') or []

        for c in graphics:
            if not get_inxi(c, "Device") or not get_inxi(c, "vendor"):
                continue

            self.components.append(
                {
                    "type": "GraphicCard",
                    "memory": self.get_memory_video(c),
                    "manufacturer": get_inxi(c, "vendor"),
                    "model": get_inxi(c, "Device"),
                    "arch": get_inxi(c, "arch"),
                    "serialNumber": get_inxi(c, "serial"),
                    "integrated": True if get_inxi(c, "port") else False
                }
            )

    def get_battery(self):
        bats = get_inxi_key(self.inxi, 'Battery') or []
        for b in bats:
            self.components.append(
                {
                    "type": "Battery",
                    "model": get_inxi(b, "model"),
                    "serialNumber": get_inxi(b, "serial"),
                    "condition": get_inxi(b, "condition"),
                    "cycles": get_inxi(b, "cycles"),
                    "volts": get_inxi(b, "volts")
                }
            )

    def get_memory_video(self, c):
        memory = get_inxi_key(self.inxi, 'Memory') or []

        for m in memory:
            igpu = get_inxi(m, "igpu")
            agpu = get_inxi(m, "agpu")
            ngpu = get_inxi(m, "ngpu")
            gpu = get_inxi(m, "gpu")
            if igpu or agpu or gpu or ngpu:
                return igpu or agpu or gpu or ngpu

        return self.default

    def get_data_storage(self):
        hdds= get_inxi_key(self.inxi, 'Drives') or []
        for d in hdds:
            usb = get_inxi(d, "type")
            if usb == "USB":
                continue

            serial = get_inxi(d, "serial")
            if serial:
                hd = {
                    "type": "Storage",
                    "manufacturer": get_inxi(d, "vendor"),
                    "model": get_inxi(d, "model"),
                    "serialNumber": get_inxi(d, "serial"),
                    "size": get_inxi(d, "size"),
                    "speed": get_inxi(d, "speed"),
                    "interface": get_inxi(d, "tech"),
                    "firmware": get_inxi(d, "fw-rev")
                }
                rpm = get_inxi(d, "rpm")
                if rpm:
                    hd["rpm"] = rpm

                family = get_inxi(d, "family")
                if family:
                    hd["family"] = family

                sata = get_inxi(d, "sata")
                if sata:
                    hd["sata"] = sata

                continue


            cycles = get_inxi(d, "cycles")
            if cycles:
                hd['cycles'] = cycles
                hd["health"] = get_inxi(d, "health")
                hd["time of used"] = get_inxi(d, "on")
                hd["read used"] = get_inxi(d, "read-units")
                hd["written used"] = get_inxi(d, "written-units")

                self.components.append(hd)
                continue

            hd = {}

    def sanitize(self, action):
        return []

    def get_networks(self):
        nets = get_inxi_key(self.inxi, "Network") or []
        for i in range(0, len(nets)-1):
            n = nets[i]
            model = get_inxi(n, "Device")
            if not model:
                continue

            interface = ''
            for k in n.keys():
                if "port" in k:
                    interface = "Integrated"
                if "pcie" in k:
                    interface = "PciExpress"
                if get_inxi(n, "type") == "USB":
                    interface = "USB"

            manufacturer = get_inxi(n, "manufacturer")
            speed = get_inxi(n, "speed")
            mac = ""

            if len(nets) > i+1:
                iface = nets[i+1]
                mac = get_inxi(iface, 'mac')
                if not speed:
                    speed = get_inxi(iface, "speed")

            self.components.append({
                    "type": "NetworkAdapter",
                    "model": model,
                    "manufacturer": manufacturer,
                    "serialNumber": mac,
                    "speed": speed,
                    "interface": interface,
                })


    def get_sound_card(self):
        audio = get_inxi_key(self.inxi, "Audio") or []

        for c in audio:
            model = get_inxi(c, "Device")
            if not model:
                continue

            self.components.append(
                {
                    "type": "SoundCard",
                    "model": model,
                    "manufacturer": get_inxi(c, 'vendor'),
                    "serialNumber": get_inxi(c, 'serial'),
                }
            )

    def get_display(self):
        graphics = get_inxi_key(self.inxi, "Graphics") or []
        for c in graphics:
            if not get_inxi(c, "Monitor"):
                continue

            self.components.append(
                {
                    "type": "Display",
                    "model": get_inxi(c, "model"),
                    "manufacturer": get_inxi(c, "vendor"),
                    "serialNumber": get_inxi(c, "serial"),
                    'size': get_inxi(c, "size"),
                    'diagonal': get_inxi(c, "diag"),
                    'resolution': get_inxi(c, "res"),
                    "date": get_inxi(c, "built"),
                    'ratio': get_inxi(c, "ratio"),
                }
            )

    def get_usb_num(self):
        return len(
            [
                u
                for u in self.dmi.get("Port Connector")
                if "USB" in u.get("Port Type", "").upper()
            ]
        )

    def get_serial_num(self):
        return len(
            [
                u
                for u in self.dmi.get("Port Connector")
                if "SERIAL" in u.get("Port Type", "").upper()
            ]
        )

    def get_firmware_num(self):
        return len(
            [
                u
                for u in self.dmi.get("Port Connector")
                if "FIRMWARE" in u.get("Port Type", "").upper()
            ]
        )

    def get_pcmcia_num(self):
        return len(
            [
                u
                for u in self.dmi.get("Port Connector")
                if "PCMCIA" in u.get("Port Type", "").upper()
            ]
        )

    def get_bios_version(self):
        return self.dmi.get("BIOS")[0].get("BIOS Revision", '1')

    def loads(self, x):
        if isinstance(x, str):
            try:
                return json.loads(x)
            except Exception as ss:
                logger.warning("%s", ss)
                return {}
        return x

    def errors(self, txt=None):
        if not txt:
            return self._errors

        logger.error(txt)
        self._errors.append("%s", txt)
