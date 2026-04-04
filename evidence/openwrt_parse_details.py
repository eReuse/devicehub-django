import json
import logging


logger = logging.getLogger('django')


class ParseSnapshot:
    """
    Parse an OpenWrt router snapshot into device and component structures
    compatible with the existing DeviceHub data model.

    Maps OpenWrt-specific data (ubus, iwinfo, /proc, /sys) to standard
    component types: Processor, RamModule, NetworkAdapter, Storage, etc.
    """

    def __init__(self, snapshot, default="n/a"):
        self.default = default
        self.snapshot = snapshot
        self.data = snapshot.get("data", {})

        self.device = {"actions": []}
        self.components = []

        self.set_computer()
        self.set_components()

        self.snapshot_json = {
            "type": "Snapshot",
            "device": self.device,
            "software": snapshot.get("software", "workbench-script-openwrt"),
            "components": self.components,
            "uuid": snapshot.get("uuid", ""),
            "endTime": snapshot.get("timestamp", ""),
            "elapsed": 1,
        }

    def set_computer(self):
        """Extract top-level device identity from board info."""
        board = self.data.get("board", {})
        device_tree = self.data.get("device_tree", {})

        model_full = board.get("model", "") or device_tree.get("model", "")
        compatible = device_tree.get("compatible", "")

        if model_full:
            parts = model_full.split()
            self.device["manufacturer"] = parts[0] if parts else ""
            self.device["model"] = model_full
        elif compatible:
            compat_parts = compatible.split(",")
            self.device["manufacturer"] = (
                compat_parts[0].capitalize() if compat_parts else ""
            )
            self.device["model"] = compatible

        self.device["type"] = "Router"
        self.device["chassis"] = "Router"

        # Use board_name as serialNumber (routers lack accessible S/N)
        self.device["serialNumber"] = board.get("board_name", "")

        release = board.get("release", {})
        self.device["version"] = release.get("version", "")
        self.device["system"] = board.get("system", "")
        self.device["kernel"] = board.get("kernel", "")

        # OpenWrt-specific metadata
        self.device["openwrt"] = {
            "target": release.get("target", ""),
            "revision": release.get("revision", ""),
            "description": release.get("description", ""),
            "hostname": board.get("hostname", ""),
            "rootfs_type": board.get("rootfs_type", ""),
        }

    def set_components(self):
        """Extract all hardware components."""
        self.get_cpu()
        self.get_ram()
        self.get_storage()
        self.get_networks()
        self.get_wifi_radios()
        self.get_thermal()

    def get_cpu(self):
        """Extract CPU info from the snapshot."""
        cpu_data = self.data.get("cpu", {})
        if not cpu_data:
            return

        # Map ARM CPU part IDs to human-readable names
        cpu_part_names = {
            "0xd03": "Cortex-A53",
            "0xd04": "Cortex-A35",
            "0xd05": "Cortex-A55",
            "0xd07": "Cortex-A57",
            "0xd08": "Cortex-A72",
            "0xd09": "Cortex-A73",
            "0xd0a": "Cortex-A75",
            "0xd0b": "Cortex-A76",
            "0xd0d": "Cortex-A77",
            "0xd40": "Neoverse-V1",
            "0xd41": "Cortex-A78",
            "0xd44": "Cortex-X1",
        }

        model = cpu_data.get("model", "")
        # Try to resolve ARM CPU part to a friendly name
        if model in cpu_part_names:
            model = cpu_part_names[model]

        # Augment with SoC info from device tree if available
        device_tree = self.data.get("device_tree", {})
        compatible = device_tree.get("compatible", "")
        soc_info = ""
        if compatible:
            # e.g. "cudy,wr3000e-v1,mediatek,mt7981" -> "mediatek mt7981"
            parts = compatible.split(",")
            if len(parts) >= 4:
                soc_info = "{} {}".format(parts[2], parts[3])
            elif len(parts) >= 2:
                soc_info = parts[-1]

        arch_map = {"8": "aarch64", "7": "armv7", "6": "armv6"}
        arch = cpu_data.get("architecture", "")
        arch_name = arch_map.get(arch, arch)

        self.components.append({
            "type": "Processor",
            "model": model,
            "manufacturer": soc_info,
            "arch": arch_name,
            "cores": str(cpu_data.get("num_cores", "")),
            "threads": str(cpu_data.get("num_cores", "")),
            "bogomips": cpu_data.get("bogomips", ""),
            "features": cpu_data.get("features", ""),
        })

    def get_ram(self):
        """Extract RAM info from memory data."""
        memory = self.data.get("memory", {})
        if not memory:
            return

        total_kb = memory.get("total_kb", 0)
        if total_kb:
            # Convert to MiB for display consistency
            total_mib = round(total_kb / 1024)
            self.components.append({
                "type": "RamModule",
                "size": "{} MiB".format(total_mib),
                "manufacturer": "",
                "model": "Embedded RAM",
                "serialNumber": "",
                "speed": "",
                "interface": "Embedded",
            })

    def get_storage(self):
        """Extract flash storage info from MTD and UBI data."""
        storage = self.data.get("storage", {})
        if not storage:
            return

        # Calculate total flash size from MTD partitions
        mtd_parts = storage.get("mtd", [])
        total_flash = sum(p.get("size_bytes", 0) for p in mtd_parts)

        if total_flash:
            total_mib = round(total_flash / (1024 * 1024))
            self.components.append({
                "type": "Storage",
                "model": "Flash NAND",
                "manufacturer": "",
                "serialNumber": "",
                "size": "{} MiB".format(total_mib),
                "interface": "MTD/UBI",
                "tech": "Flash",
                "partitions": len(mtd_parts),
            })

    def get_networks(self):
        """Extract network adapter info from interfaces."""
        network = self.data.get("network", {})
        interfaces = network.get("interfaces", [])

        # Group interfaces to avoid listing all virtual sub-interfaces
        # Focus on physical interfaces (eth0, wan) and bridges (br-lan)
        seen_macs = set()

        for iface in interfaces:
            name = iface.get("name", "")
            mac = iface.get("mac", "")

            # Skip interfaces without MAC or with zero MAC
            if not mac or mac == "00:00:00:00:00:00":
                continue

            # Only list primary physical and bridge interfaces
            # Skip virtual sub-interfaces (lan1@eth0, lan2@eth0, etc.)
            if name not in ("eth0", "wan", "br-lan"):
                continue

            if mac in seen_macs:
                continue
            seen_macs.add(mac)

            speed = iface.get("speed_mbps")
            speed_str = "{} Mbps".format(speed) if speed else ""

            self.components.append({
                "type": "NetworkAdapter",
                "model": name,
                "manufacturer": "",
                "serialNumber": mac,
                "speed": speed_str,
                "interface": "Integrated",
            })

    def get_wifi_radios(self):
        """Extract WiFi radio info as network adapters."""
        wifi = self.data.get("wifi", {})
        wifi_ifaces = wifi.get("interfaces", [])

        for iface in wifi_ifaces:
            hw = iface.get("hardware", "")
            if not hw:
                continue

            band_info = ""
            freq = iface.get("frequency_ghz", "")
            hw_modes = iface.get("hw_modes", "")
            if freq:
                band_info = "{} GHz".format(freq)

            model = hw
            if hw_modes:
                model = "{} ({})".format(hw, hw_modes)

            self.components.append({
                "type": "WiFiAccessPoint",
                "model": model,
                "manufacturer": hw.split()[0] if hw else "",
                "serialNumber": "",
                "speed": band_info,
                "interface": "Wireless",
                "mode": iface.get("mode", ""),
                "channel": iface.get("channel", 0),
            })

    def get_thermal(self):
        """Store thermal data as device metadata (not a component)."""
        thermal = self.data.get("thermal", [])
        if thermal and len(thermal) > 0:
            temp_mc = thermal[0].get("temp_millicelsius", 0)
            if temp_mc:
                self.device["temperature_celsius"] = round(temp_mc / 1000, 1)
