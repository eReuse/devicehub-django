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
    Extracts evidence data from a device, including power-on hours and disk metadata.

    Args:
        device: Device object with evidences

    Returns:
        List of EvidenceData objects sorted chronologically
    """

    # When root aliases exist, device.evidences contains evidences from multiple devices.
    # For environmental impact, we only want evidences from the ACTUAL device being viewed,
    # not from its aliases. Filter by checking if the evidence UUID has a property with
    # the device's ID (not alias IDs).
    from evidence.models import SystemProperty
    
    filtered_evidences = []
    for evidence in device.evidences:
        # Check if this evidence has a property matching the device ID
        has_device_property = SystemProperty.objects.filter(
            uuid=evidence.uuid,
            value=device.id,
            owner=device.owner
        ).exists()
        if has_device_property:
            filtered_evidences.append(evidence)
    
    # Sort evidences chronologically by their created timestamp (oldest first)
    sorted_evidences = sorted(filtered_evidences, key=lambda e: e.created or "")
    
    evidences_data = []
    # Process evidences in chronological order (oldest first)
    for idx, evidence in enumerate(sorted_evidences):
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
