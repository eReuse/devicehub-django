"""
Tests for T_R (Reuse Time) calculation.
"""

from django.test import TestCase

from environmental_impact.algorithms.ereuse2025.lifecycle_models import (
    DiskMetadata,
    EvidenceData,
)
from environmental_impact.algorithms.ereuse2025.time_calculations import (
    calculate_reuse_time,
)


class TestReuseTimeCalculation(TestCase):
    """Test T_R (Reuse Time) calculation."""

    def test_reuse_time_with_two_evidences(self):
        """Test T_R = PoH_last - PoH_first with 2 evidences."""
        disk = DiskMetadata("SN123", "Model-X", "Manufacturer-A")
        evidences = [
            EvidenceData("uuid1", 0, 1000, disk),
            EvidenceData("uuid2", 1, 2000, disk)
        ]
        t_r = calculate_reuse_time(evidences)
        # T_R = 2000 - 1000 = 1000
        self.assertEqual(t_r, 1000)

    def test_reuse_time_with_multiple_evidences(self):
        """Test T_R with multiple evidences."""
        disk = DiskMetadata("SN123", "Model-X", "Manufacturer-A")
        evidences = [
            EvidenceData("uuid1", 0, 1000, disk),
            EvidenceData("uuid2", 1, 1500, disk),
            EvidenceData("uuid3", 2, 2000, disk),
            EvidenceData("uuid4", 3, 2500, disk)
        ]
        t_r = calculate_reuse_time(evidences)
        # T_R = 2500 - 1000 = 1500
        self.assertEqual(t_r, 1500)

    def test_reuse_time_with_disk_changes(self):
        """Test that T_R calculation ignores disk changes."""
        disk1 = DiskMetadata("SN123", "Model-X", "Manufacturer-A")
        disk2 = DiskMetadata("SN456", "Model-Y", "Manufacturer-B")

        evidences = [
            EvidenceData("uuid1", 0, 1000, disk1),
            EvidenceData("uuid2", 1, 1500, disk1),
            EvidenceData("uuid3", 2, 500, disk2),  # Disk change
            EvidenceData("uuid4", 3, 800, disk2),
        ]
        t_r = calculate_reuse_time(evidences)
        # T_R = PoH_last - PoH_first = 800 - 1000
        # Note: This might be negative, which is handled in validation
        self.assertEqual(t_r, -200)

    def test_reuse_time_with_single_evidence(self):
        """Test T_R returns 0 with single evidence."""
        disk = DiskMetadata("SN123", "Model-X", "Manufacturer-A")
        evidences = [EvidenceData("uuid1", 0, 1000, disk)]
        t_r = calculate_reuse_time(evidences)
        self.assertEqual(t_r, 0)
