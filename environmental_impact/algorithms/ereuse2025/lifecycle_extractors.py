"""
Extraction utilities for lifecycle data from device evidences.
"""

from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict
from device.models import Device
from .. import common
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


def get_evidence_datetime(evidence) -> Optional[datetime]:
    """Return when the evidence was taken, as an aware UTC datetime.

    Snapshot formats disagree on timezones: legacy Workbench sends
    ``...Z``/``+00:00`` while workbench-script sends naive local time.
    Aware and naive datetimes cannot be compared, so naive values are
    read as UTC. The upload time is only used when the document has no
    usable date of its own.
    """
    timestamp_candidates = [
        lambda: evidence.doc.get("endTime"),
        lambda: evidence.doc.get("timestamp"),
        lambda: evidence.doc.get("date"),
        evidence.get_time_created,
    ]

    for get_value in timestamp_candidates:
        value = get_value()
        if not value:
            continue
        try:
            parsed = datetime.fromisoformat(str(value))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    return None


def _get_evidence_sort_key(evidence) -> tuple[int, object]:
    evidence_datetime = get_evidence_datetime(evidence)
    if evidence_datetime:
        return (0, evidence_datetime)
    return (1, str(evidence.uuid))


def get_evidences_data_from_device(device: Device) -> List[EvidenceData]:
    """
    Extract all evidences from a device as EvidenceData objects.

    Args:
        device: Device object with evidences

    Returns:
        List of EvidenceData objects sorted chronologically
    """

    evidences_data = []
    evidences_in_chronological_order = sorted(device.evidences, key=_get_evidence_sort_key)

    for idx, evidence in enumerate(evidences_in_chronological_order):
        components = evidence.get_components()
        poh = common.get_poh_from_evidence(evidence)
        disk_metadata = DiskMetadata("", "", "")
        # Only process if not legacy (inxi present)
        if getattr(evidence, "inxi", None) or poh:
            storage_poh, candidate_comp = _find_storage_with_poh(components)
            if storage_poh:
                poh = storage_poh
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
