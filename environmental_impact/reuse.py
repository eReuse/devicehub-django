"""Where a device's second life starts.

A device counts as reused once it has a second evidence: the span from its
first evidence (intake at the refurbisher) onwards is its second life. A manager
can override that with a manual mark on the evidence where reuse starts, e.g.
when a device was scanned twice before delivery, or delivered and not re-scanned
yet. Marks are stored like the social-impact flags: one ``UserProperty`` per
marked evidence, keyed on that evidence's own uuid.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from evidence.models import UserProperty

if TYPE_CHECKING:
    from device.models import Device
    from user.models import Institution


REUSE_START_KEY = "impact:reuse_start"
TRUE_VALUE = "yes"

SOURCE_MARK = "mark"
SOURCE_SECOND_EVIDENCE = "second_evidence"


def read_reuse_marks(device: "Device", institution: "Institution") -> set[str]:
    uuids = device.uuids or []
    if not uuids or institution is None:
        return set()
    rows = UserProperty.objects.filter(
        uuid__in=uuids, owner=institution, key=REUSE_START_KEY
    ).values_list("uuid", "value")
    return {str(u) for u, v in rows if (v or "").strip().lower() == TRUE_VALUE}


def resolve_reuse_start(ordered_uuids: list[str], marks: set[str]) -> tuple[int | None, str | None]:
    """Index in the chronological timeline where the second life starts.

    A manual mark wins (the earliest one, if several). Without marks, a second
    evidence means reuse started at the first one.
    """
    for index, uuid in enumerate(ordered_uuids):
        if uuid in marks:
            return index, SOURCE_MARK
    if len(ordered_uuids) >= 2:
        return 0, SOURCE_SECOND_EVIDENCE
    return None, None


def save_reuse_mark(device: "Device", institution: "Institution", user, evidence_uuid: str | None) -> None:
    """Replace the device's reuse mark; ``None`` clears it (back to automatic)."""
    UserProperty.objects.filter(
        uuid__in=device.uuids or [], owner=institution, key=REUSE_START_KEY
    ).delete()
    if evidence_uuid:
        UserProperty.objects.create(
            uuid=evidence_uuid,
            key=REUSE_START_KEY,
            value=TRUE_VALUE,
            owner=institution,
            user=user,
            type=UserProperty.Type.USER,
        )
