"""
Extraction utilities for lifecycle data from device evidences.
"""

from typing import List, Optional, Tuple, Dict
from device.models import Device
from ..common import convert_str_time_to_hours
from .lifecycle_models import EvidenceData, DiskMetadata


def _find_storage_with_poh(components: List[Dict]) -> Tuple[int, Optional[Dict]]:
    """Try to find storage component that has usage time."""
    if components:
        for comp in components:
            if comp.get("type") == "Storage":
                str_time = comp.get("time of used", "")
                if str_time:
                    return convert_str_time_to_hours(str_time), comp
    return 0, None


def _find_first_storage(components: List[Dict]) -> Optional[Dict]:
    """Find the first storage component as fallback."""
    if components:
        for comp in components:
            if comp.get("type") == "Storage":
                return comp
    return None


def get_evidences_data_from_device(device: Device) -> List[EvidenceData]:
    """
    Extract all evidences from a device as EvidenceData objects.

    Args:
        device: Device object with evidences

    Returns:
        List of EvidenceData objects sorted chronologically
    """

    evidences_data = []
    # We want chronological order (oldest first)
    for idx, evidence in enumerate(reversed(device.evidences)):
        components = evidence.get_components()
        poh = 0
        disk_metadata = DiskMetadata("", "", "")
        # Only process if not legacy (inxi present)
        if getattr(evidence, "inxi", None):
            poh, candidate_comp = _find_storage_with_poh(components)
            if not candidate_comp:
                candidate_comp = _find_first_storage(components)
            if candidate_comp:
                disk_metadata = DiskMetadata(
                    serial=candidate_comp.get("serialNumber", ""),
                    model=candidate_comp.get("model", ""),
                    manufacturer=candidate_comp.get("manufacturer", ""),
                )
        evidences_data.append(
            EvidenceData(
                uuid=evidence.uuid,
                index=idx,
                poh=poh,
                disk_metadata=disk_metadata,
            )
        )
    return evidences_data
