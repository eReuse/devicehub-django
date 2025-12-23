from django.test import TestCase

from environmental_impact.algorithms.ereuse2025.lifecycle_models import (
    DiskMetadata,
    EvidenceData,
)
from environmental_impact.algorithms.ereuse2025.disk_change_detector import (
    detect_disk_changes,
)


class TestDiskChangeDetection(TestCase):
    def test_no_disk_changes_with_two_evidences(self):
        """Test no changes detected with same disk across 2 evidences."""
        disk = DiskMetadata("SN123", "Model-X", "Manufacturer-A")
        evidences = [
            EvidenceData("uuid1", 0, 1000, disk),
            EvidenceData("uuid2", 1, 2000, disk),
        ]
        changes = detect_disk_changes(evidences)
        self.assertEqual(changes, [])

    def test_disk_change_detected_at_second_evidence(self):
        """Test disk change detected at second evidence."""
        disk1 = DiskMetadata("SN123", "Model-X", "Manufacturer-A")
        disk2 = DiskMetadata("SN456", "Model-Y", "Manufacturer-B")
        evidences = [
            EvidenceData("uuid1", 0, 1000, disk1),
            EvidenceData("uuid2", 1, 500, disk2),
        ]
        changes = detect_disk_changes(evidences)
        self.assertEqual(changes, [1])

    def test_multiple_disk_changes(self):
        """Test multiple disk changes detected correctly."""
        disk1 = DiskMetadata("SN123", "Model-X", "Manufacturer-A")
        disk2 = DiskMetadata("SN456", "Model-Y", "Manufacturer-B")
        disk3 = DiskMetadata("SN789", "Model-Z", "Manufacturer-C")

        evidences = [
            EvidenceData("uuid1", 0, 1000, disk1),
            EvidenceData("uuid2", 1, 1500, disk1),
            EvidenceData("uuid3", 2, 500, disk2),  # Change at index 2
            EvidenceData("uuid4", 3, 800, disk2),
            EvidenceData("uuid5", 4, 300, disk3),  # Change at index 4
            EvidenceData("uuid6", 5, 600, disk3),
        ]
        changes = detect_disk_changes(evidences)
        self.assertEqual(changes, [2, 4])

    def test_no_changes_with_single_evidence(self):
        """Test no changes with only one evidence."""
        disk = DiskMetadata("SN123", "Model-X", "Manufacturer-A")
        evidences = [EvidenceData("uuid1", 0, 1000, disk)]
        changes = detect_disk_changes(evidences)
        self.assertEqual(changes, [])
