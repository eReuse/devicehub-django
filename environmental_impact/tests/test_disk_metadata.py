from django.test import TestCase

from environmental_impact.algorithms.ereuse2025.lifecycle_models import (
    DiskMetadata,
)


class TestDiskMetadata(TestCase):
    """Test disk metadata comparison logic."""

    def test_disk_metadata_equality(self):
        """Test that identical disks are equal."""
        disk1 = DiskMetadata("SN123", "Model-X", "Manufacturer-A")
        disk2 = DiskMetadata("SN123", "Model-X", "Manufacturer-A")
        self.assertEqual(disk1, disk2)

    def test_disk_metadata_inequality(self):
        """Test that different disks are not equal."""
        disk1 = DiskMetadata("SN123", "Model-X", "Manufacturer-A")
        disk2 = DiskMetadata("SN456", "Model-Y", "Manufacturer-B")
        self.assertNotEqual(disk1, disk2)

    def test_disk_metadata_is_empty(self):
        """Test empty disk detection."""
        empty_disk = DiskMetadata("", "", "")
        self.assertTrue(empty_disk.is_empty())

        valid_disk = DiskMetadata("SN123", "", "")
        self.assertFalse(valid_disk.is_empty())
