from unittest.mock import Mock
from django.test import TestCase

from environmental_impact.algorithms.common import (
    get_poh_from_device,
    extract_disk_metadata_from_components,
)


class TestComponentExtraction(TestCase):
    """Test extraction of PoH and disk metadata from components."""

    def test_get_power_on_hours_from_device(self):
        """Test PoH extraction from device with storage component."""
        # Create mock device with evidence and components
        device = Mock()
        device.last_evidence = Mock()
        device.last_evidence.inxi = True  # Modern inxi-based evidence
        components = [
            {"type": "Processor", "model": "Intel i5"},
            {"type": "Storage", "time of used": "1000d 12h", "model": "SSD"},
        ]
        device.last_evidence.get_components = Mock(return_value=components)
        poh = get_poh_from_device(device)
        # 1000d 12h = 1000*24 + 12 = 24012 hours
        self.assertEqual(poh, 24012)

    def test_get_power_on_hours_returns_zero_when_no_storage(self):
        """Test PoH extraction returns 0 when no storage found."""
        # Create mock device without storage component
        device = Mock()
        device.last_evidence = Mock()
        device.last_evidence.inxi = True
        components = [
            {"type": "Processor", "model": "Intel i5"},
        ]
        device.last_evidence.get_components = Mock(return_value=components)

        poh = get_poh_from_device(device)
        self.assertEqual(poh, 0)

    def test_get_power_on_hours_from_legacy_devices(self):
        """Legacy devices (no inxi) read the first disk that reports hours."""
        device = Mock()
        device.last_evidence = Mock()
        device.last_evidence.inxi = None  # Legacy workbench
        components = [
            {"type": "SolidStateDrive", "model": "256GB", "hours": 0},  # disk without the counter
            {"type": "SolidStateDrive", "model": "500GB", "hours": 17703},
        ]
        device.last_evidence.get_components = Mock(return_value=components)
        self.assertEqual(get_poh_from_device(device), 17703)

    def test_get_power_on_hours_legacy_without_hours_is_zero(self):
        """Legacy devices whose disks report no counter return 0."""
        device = Mock()
        device.last_evidence = Mock()
        device.last_evidence.inxi = None
        device.last_evidence.get_components = Mock(return_value=[{"type": "HardDrive", "hours": 0}])
        self.assertEqual(get_poh_from_device(device), 0)

    def test_extract_disk_metadata(self):
        """Test disk metadata extraction from storage component."""
        components = [
            {
                "type": "Storage",
                "serialNumber": "SN123",
                "model": "Samsung-SSD",
                "manufacturer": "Samsung",
            }
        ]
        metadata = extract_disk_metadata_from_components(components)
        self.assertIsNotNone(metadata)
        self.assertEqual(metadata["serial"], "SN123")
        self.assertEqual(metadata["model"], "Samsung-SSD")
        self.assertEqual(metadata["manufacturer"], "Samsung")

    def test_extract_disk_metadata_returns_none_when_missing(self):
        """Test disk metadata extraction returns None when no storage."""
        components = [
            {"type": "Processor", "model": "Intel i5"},
        ]
        metadata = extract_disk_metadata_from_components(components)
        self.assertIsNone(metadata)
