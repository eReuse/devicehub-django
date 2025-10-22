"""
Extraction utilities for lifecycle data from device evidences.
"""

from typing import List
from device.models import Device
from ..common import (
    extract_disk_metadata_from_components,
    convert_str_time_to_hours,
)
from .lifecycle_models import EvidenceData, DiskMetadata
from ..common import get_poh_from_evidence


def get_evidences_data_from_device(device: Device) -> List[EvidenceData]:
    """
    Extract all evidences from a device as EvidenceData objects.

    Args:
        device: Device object with evidences

    Returns:
        List of EvidenceData objects sorted chronologically
    """

    evidences_data = []
    for idx, evidence in enumerate(device.evidences):
        components = evidence.get_components()
        # Extract PoH from this evidence's storage components
        poh = get_poh_from_evidence(evidence)
        # Extract disk metadata from components
        disk_dict = extract_disk_metadata_from_components(components)
        if disk_dict:
            disk_metadata = DiskMetadata(
                serial=disk_dict.get("serial", ""),
                model=disk_dict.get("model", ""),
                manufacturer=disk_dict.get("manufacturer", ""),
            )
        else:
            disk_metadata = DiskMetadata("", "", "")

        evidences_data.append(
            EvidenceData(
                uuid=evidence.uuid,
                index=idx,
                poh=poh,
                disk_metadata=disk_metadata,
            )
        )

    return evidences_data
