"""
Time calculations for device lifecycle metrics.

Implements the mathematical formulas for calculating T_T (Total Usage Time)
and T_R (Reuse Time).
"""

from typing import List
from .lifecycle_models import EvidenceData


def _calculate_first_disk_usage(
    evidences_data: List[EvidenceData], first_change_index: int
) -> int:
    if first_change_index > 0:
        poh_before_change = evidences_data[first_change_index - 1].poh
        poh_first = evidences_data[0].poh
        return poh_before_change - poh_first
    return 0


def _calculate_intermediate_disks_usage(
    evidences_data: List[EvidenceData], disk_change_indices: List[int]
) -> int:
    total = 0
    for i in range(len(disk_change_indices) - 1):
        current_change = disk_change_indices[i]
        next_change = disk_change_indices[i + 1]

        if next_change - 1 >= current_change:
            poh_before_next = evidences_data[next_change - 1].poh
            poh_at_current = evidences_data[current_change].poh
            total += poh_before_next - poh_at_current
    return total


def _calculate_last_disk_usage(
    evidences_data: List[EvidenceData], last_change_index: int
) -> int:
    last_evidence_index = len(evidences_data) - 1
    if last_evidence_index >= last_change_index:
        return (
            evidences_data[last_evidence_index].poh
            - evidences_data[last_change_index].poh
        )
    return 0


def calculate_total_usage_time(
    evidences_data: List[EvidenceData], disk_change_indices: List[int]
) -> int:
    if not evidences_data:
        return 0
    if len(evidences_data) == 1:
        return evidences_data[0].poh
    if not disk_change_indices:
        return evidences_data[-1].poh

    sorted_changes = sorted(disk_change_indices)
    first_disk = _calculate_first_disk_usage(evidences_data, sorted_changes[0])
    intermediate_disks = _calculate_intermediate_disks_usage(
        evidences_data, sorted_changes
    )
    last_disk = _calculate_last_disk_usage(evidences_data, sorted_changes[-1])
    total_time = first_disk + intermediate_disks + last_disk
    return total_time


def calculate_reuse_time(evidences_data_chronological: List[EvidenceData]) -> int:

    if len(evidences_data_chronological) < 2:
        return 0

    return evidences_data_chronological[-1].poh - evidences_data_chronological[0].poh
