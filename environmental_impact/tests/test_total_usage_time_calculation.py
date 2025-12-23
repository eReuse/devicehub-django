"""
Tests for T_T (Total Usage Time) calculation.
"""

from django.test import TestCase

from environmental_impact.algorithms.ereuse2025.lifecycle_models import (
    DiskMetadata,
    EvidenceData,
)
from environmental_impact.algorithms.ereuse2025.disk_change_detector import (
    detect_disk_changes,
)
from environmental_impact.algorithms.ereuse2025.time_calculations import (
    calculate_total_usage_time,
)


class TestTotalUsageTimeCalculation(TestCase):
    """Test T_T (Total Usage Time) calculation."""

    def test_simple_case_no_disk_changes(self):
        """Test T_T with 2 evidences, no disk changes."""
        disk = DiskMetadata("SN123", "Model-X", "Manufacturer-A")
        evidences = [
            EvidenceData("uuid1", 0, 1000, disk),
            EvidenceData("uuid2", 1, 2000, disk)
        ]
        changes = detect_disk_changes(evidences)
        t_t = calculate_total_usage_time(evidences, changes)
        # T_T = PoH_last = 2000
        self.assertEqual(t_t, 2000)

    def test_multiple_evidences_no_disk_changes(self):
        """Test T_T with multiple evidences, no disk changes."""
        disk = DiskMetadata("SN123", "Model-X", "Manufacturer-A")
        evidences = [
            EvidenceData("uuid1", 0, 1000, disk),
            EvidenceData("uuid2", 1, 1500, disk),
            EvidenceData("uuid3", 2, 2000, disk),
            EvidenceData("uuid4", 3, 2500, disk)
        ]
        changes = detect_disk_changes(evidences)
        t_t = calculate_total_usage_time(evidences, changes)
        # T_T = PoH_last = 2500
        self.assertEqual(t_t, 2500)

    def test_single_disk_change(self):
        """
        Test T_T with single disk change.

        Formula: T_T = (PoH_{c1-1} - PoH_1) + (PoH_N - PoH_{c1})
        """
        disk1 = DiskMetadata("SN123", "Model-X", "Manufacturer-A")
        disk2 = DiskMetadata("SN456", "Model-Y", "Manufacturer-B")

        evidences = [
            EvidenceData("uuid1", 0, 1000, disk1),  # i
            EvidenceData("uuid2", 1, 1500, disk1),  # j (before change)
            EvidenceData("uuid3", 2, 500, disk2),   # k (disk change)
            EvidenceData("uuid4", 3, 800, disk2),   # N
        ]
        changes = detect_disk_changes(evidences)  # [2]

        # T_T = (PoH_1 - PoH_0) + (PoH_3 - PoH_2)
        #     = (1500 - 1000) + (800 - 500)
        #     = 500 + 300 = 800
        t_t = calculate_total_usage_time(evidences, changes)
        self.assertEqual(t_t, 800)

    def test_multiple_disk_changes_example_from_spec(self):
        """
        Test T_T with multiple disk changes (example from specification).

        Evidences: {i, j, k, l, m, n, o}
        Disk changes at: k (index 2), n (index 5)
        """
        disk1 = DiskMetadata("SN123", "Model-X", "Manufacturer-A")
        disk2 = DiskMetadata("SN456", "Model-Y", "Manufacturer-B")
        disk3 = DiskMetadata("SN789", "Model-Z", "Manufacturer-C")

        evidences = [
            EvidenceData("uuid_i", 0, 1000, disk1),  # i
            EvidenceData("uuid_j", 1, 1500, disk1),  # j
            EvidenceData("uuid_k", 2, 500, disk2),   # k (change)
            EvidenceData("uuid_l", 3, 800, disk2),   # l
            EvidenceData("uuid_m", 4, 1200, disk2),  # m
            EvidenceData("uuid_n", 5, 300, disk3),   # n (change)
            EvidenceData("uuid_o", 6, 600, disk3),   # o
        ]
        changes = detect_disk_changes(evidences)  # [2, 5]

        # Formula: T_T = (PoH_{c1-1} - PoH_1) +
        #                (PoH_{c2-1} - PoH_{c1}) +
        #                (PoH_N - PoH_{c2})
        # T_T = (PoH_1 - PoH_0) +
        #       (PoH_4 - PoH_2) +
        #       (PoH_6 - PoH_5)
        # T_T = (1500 - 1000) + (1200 - 500) + (600 - 300)
        # T_T = 500 + 700 + 300 = 1500
        t_t = calculate_total_usage_time(evidences, changes)
        self.assertEqual(t_t, 1500)
