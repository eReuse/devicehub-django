"""
Disk change detection for device lifecycle calculations.

Detects when a disk has been replaced by comparing metadata across
consecutive evidences.
"""

from typing import List
from .lifecycle_models import EvidenceData


def detect_disk_changes(
    evidences_data: List[EvidenceData]
) -> List[int]:
    """
    Detect disk changes across evidences.

    A disk change is detected when disk metadata (model, manufacturer,
    serialNumber) differs between consecutive evidences.

    Args:
        evidences_data: List of EvidenceData sorted chronologically

    Returns:
        List of indices where disk changes were detected (0-based)
    """
    if len(evidences_data) < 2:
        return []

    disk_change_indices = []
    prev_disk = evidences_data[0].disk_metadata

    for i in range(1, len(evidences_data)):
        curr_disk = evidences_data[i].disk_metadata

        # Skip if current disk metadata is empty
        if curr_disk and curr_disk.is_empty():
            continue

        # Detect change if metadata differs
        if prev_disk and curr_disk and prev_disk != curr_disk:
            disk_change_indices.append(i)
            prev_disk = curr_disk
        elif not prev_disk and curr_disk:
            # First disk detected
            prev_disk = curr_disk

    return disk_change_indices
