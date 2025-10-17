#!/usr/bin/env python3
import logging
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger('django')

class ParseSnapshot:
    def __init__(self, snapshot, default="n/a"):
        self.default = default
        data = snapshot.get("credentialSubject", snapshot)

        smartctl_data = data.get("data", {}).get("smartctl", {})
        if not isinstance(smartctl_data, dict):
            logger.error("smartctl data is not in the expected dictionary format.")
            smartctl_data = {}

        self.device = {"actions": []}
        self.components = self._parse_smartctl(smartctl_data)

        self.snapshot_json = {
            "type": "Snapshot",
            "device": self.device,
            "components": self.components,
            "uuid": data.get("uuid", self.default),
            "endTime": data.get("timestamp", self.default),
            "elapsed": 1,
        }

    def _parse_smartctl(self, smartctl_data):
        if not smartctl_data:
            return []

        ata_attributes = smartctl_data.get("ata_smart_attributes", {}).get("table", [])
        attr_map = {
            attr.get("id"): attr.get("raw", {}).get("value")
            for attr in ata_attributes
        }

        rotation_rate = smartctl_data.get("rotation_rate")
        device_type = "SolidStateDrive" if rotation_rate is None or rotation_rate == 0 else "HardDrive"

        capacity_bytes = smartctl_data.get("user_capacity", {}).get("bytes")
        capacity_gb = round(capacity_bytes / (10**9), 2) if capacity_bytes else None

        smart_status = smartctl_data.get("smart_status", {})
        health_status = "PASSED" if smart_status.get("passed") else ("FAILED" if smart_status.get("passed") is False else "Unknown")

        info = {
            # Core
            _("Device Type"): device_type,
            _("Manufacturer"): smartctl_data.get("model_family"),
            _("Model"): smartctl_data.get("model_name"),
            _("Serial Number"): smartctl_data.get("serial_number"),
            _("Firmware Version"): smartctl_data.get("firmware_version"),
            _("Capacity (GB)"): capacity_gb,
            _("Capacity (bytes)"): capacity_bytes,
            _("Form Factor"): smartctl_data.get("form_factor", {}).get("name"),
            _("Interface Speed"): smartctl_data.get("interface_speed", {}).get("current", {}).get("string"),
            _("SATA Version"): smartctl_data.get("sata_version", {}).get("string"),
            _("Rotation Rate (RPM)"): rotation_rate,

            # Health Data
            _("Health Status"): health_status,
            _("Power On Hours"): smartctl_data.get("power_on_time", {}).get("hours"),
            _("Reallocated Sector Count"): attr_map.get(5),
            _("Current Pending Sector Count"): attr_map.get(197),
            _("Offline Uncorrectable Sector Count"): attr_map.get(198),

            # SSD-specific data
            _("SSD Percentage Used (NVMe)"): smartctl_data.get("nvme_smart_health_information_log", {}).get("percentage_used"),
            _("SSD Wear Indicator (SATA)"): attr_map.get(233),
        }

        return [{k: v} for k, v in info.items() if v is not None]
