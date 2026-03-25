import logging

from evidence.mixin_parse import BuildMix


logger = logging.getLogger('django')


class Build(BuildMix):
    """
    Parser for OpenWrt router snapshots produced by workbench-script-openwrt.

    Extracts device identity fields from the OpenWrt-specific data structure
    (ubus board info, device tree, network interfaces) to generate CHIDs
    compatible with the existing algorithm.
    """

    def get_details(self):
        data = self.json.get("data", {})
        board = data.get("board", {})
        device_tree = data.get("device_tree", {})
        network = data.get("network", {})

        # Manufacturer: extract from board model or device tree compatible
        # e.g. "Cudy WR3000E v1" -> "Cudy", or from compatible "cudy,wr3000e-v1"
        model_full = board.get("model", "") or device_tree.get("model", "")
        compatible = device_tree.get("compatible", "")

        if model_full:
            # First word of the model string is typically the manufacturer
            parts = model_full.split()
            self.manufacturer = parts[0] if parts else ""
            self.model = model_full
        elif compatible:
            # Parse from device tree compatible string, e.g. "cudy,wr3000e-v1"
            compat_parts = compatible.split(",")
            self.manufacturer = compat_parts[0].capitalize() if compat_parts else ""
            self.model = compatible

        # Serial number: use board_name as a stable identifier
        # Routers typically don't have unique serial numbers accessible via software
        self.serial_number = board.get("board_name", "")

        # Type and chassis
        self.type = "Router"
        self.chassis = "Router"

        # Version: OpenWrt release version
        release = board.get("release", {})
        self.version = release.get("version", "")

        # MAC address: use the first physical network interface MAC
        # Prefer WAN port MAC as it's typically the "base" MAC
        self.mac = self._get_primary_mac(network)

        if not self.mac:
            txt = "Could not retrieve MAC address in OpenWrt snapshot %s"
            logger.warning(txt, self.uuid)

    def _get_primary_mac(self, network):
        """
        Get the primary MAC address from network interfaces.
        Prefer eth0 or wan interface as these typically hold the base MAC.
        """
        interfaces = network.get("interfaces", [])
        mac_map = {}

        for iface in interfaces:
            name = iface.get("name", "")
            mac = iface.get("mac", "")
            if mac and mac != "00:00:00:00:00:00":
                mac_map[name] = mac

        # Priority order for selecting the primary MAC
        for preferred in ["eth0", "wan", "br-lan", "lan1"]:
            if preferred in mac_map:
                return mac_map[preferred]

        # Fallback: first non-zero MAC found
        if mac_map:
            return next(iter(mac_map.values()))

        return ""

    def _get_components(self):
        from evidence.openwrt_parse_details import ParseSnapshot
        data = ParseSnapshot(self.json)
        self.device = data.device
        self.components = data.components

        self.device.pop("actions", None)
        for c in self.components:
            c.pop("actions", None)
