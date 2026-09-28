"""Where a device's second life starts, and whether it went to recycling.

A device leaves the refurbisher in one of four ways DeviceHub can see. They
are checked in this order and the first one wins:

1. **Manual mark** on the evidence where reuse starts (operator correction).
   Stored like the social-impact flags: one ``UserProperty`` per marked
   evidence, keyed on that evidence's own uuid.
2. **Transfer state**, e.g. the default ``DONATION`` state, on one device sold
   or donated on its own. Reuse starts at the evidence the state was set on.
3. **Salida lot**: the device is in an outgoing lot. Lot membership has no
   date, so reuse starts at the last evidence before the lot was created.
4. **Second evidence**: the device was scanned again in its second life, so
   reuse started at its first evidence (intake).

A state whose disposition is ``recycled`` or ``disposed`` (the default
``DISMANTLE``) ends the device's life. With one of the explicit signals 1-3
before it, the device was reused and its second life has ended; otherwise it
went to recycling without a second life. Signal 4 does not count here: a
device scanned twice in the workshop and then dismantled was never reused.

States are recognised by their DTE configuration (UNTP event type and
disposition, set in admin), and only when a state has none, by the default
names ``DONATION`` and ``DISMANTLE``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from evidence.models import UserProperty

if TYPE_CHECKING:
    from device.models import Device
    from user.models import Institution


REUSE_START_KEY = "impact:reuse_start"
TRUE_VALUE = "yes"

SOURCE_MARK = "mark"
SOURCE_TRANSFER_STATE = "transfer_state"
SOURCE_OUTGOING_LOT = "outgoing_lot"
SOURCE_SECOND_EVIDENCE = "second_evidence"
EXPLICIT_SOURCES = (SOURCE_MARK, SOURCE_TRANSFER_STATE, SOURCE_OUTGOING_LOT)

END_OF_LIFE_DISPOSITIONS = {"recycled", "disposed"}
TRANSFER_EVENT = "MoveEvent"
DEFAULT_TRANSFER_STATE = "DONATION"
DEFAULT_END_OF_LIFE_STATE = "DISMANTLE"

# Lot tags are free text per institution; these are the default names.
OUTGOING_TAG_NAMES = {"salida", "sortida", "outgoing", "out"}
INCOMING_TAG_NAMES = {"entrada", "incoming", "in"}


@dataclass
class ReuseSignals:
    marks: set
    transfer_uuid: str | None = None
    outgoing_since: datetime | None = None
    end_of_life: bool = False


def lot_direction(tag_name: str | None) -> str | None:
    """"incoming" | "outgoing" | None for a lot tag name."""
    name = (tag_name or "").strip().lower()
    if name in INCOMING_TAG_NAMES:
        return "incoming"
    if name in OUTGOING_TAG_NAMES:
        return "outgoing"
    return None


def classify_state(name: str, dte_config: dict | None) -> str | None:
    """"transfer" | "end_of_life" | None for a state definition."""
    config = dte_config or {}
    disposition = (config.get("disposition") or "").strip()
    event_type = (config.get("event_type") or "").strip()
    if disposition in END_OF_LIFE_DISPOSITIONS:
        return "end_of_life"
    if event_type == TRANSFER_EVENT:
        return "transfer"
    if not disposition and not event_type:
        upper = (name or "").strip().upper()
        if upper == DEFAULT_END_OF_LIFE_STATE:
            return "end_of_life"
        if upper == DEFAULT_TRANSFER_STATE:
            return "transfer"
    return None


def read_reuse_marks(device: "Device", institution: "Institution") -> set[str]:
    uuids = device.uuids or []
    if not uuids or institution is None:
        return set()
    rows = UserProperty.objects.filter(
        uuid__in=uuids, owner=institution, key=REUSE_START_KEY
    ).values_list("uuid", "value")
    return {str(u) for u, v in rows if (v or "").strip().lower() == TRUE_VALUE}


def read_reuse_signals(device: "Device", institution: "Institution") -> ReuseSignals:
    from action.models import State, StateDefinition
    from evidence.models import RootAlias
    from lot.models import DeviceLot

    signals = ReuseSignals(marks=read_reuse_marks(device, institution))
    uuids = device.uuids or []
    if institution is None or not uuids:
        return signals

    definitions = {
        d.state: d.dte_config for d in StateDefinition.objects.filter(institution=institution)
    }
    states = State.objects.filter(snapshot_uuid__in=uuids, institution=institution).order_by("date")
    kinds = [(classify_state(s.state, definitions.get(s.state)), s) for s in states]
    for kind, state in kinds:
        if kind == "transfer":
            signals.transfer_uuid = str(state.snapshot_uuid)
            break
    if kinds and kinds[-1][0] == "end_of_life":
        signals.end_of_life = True

    lots = DeviceLot.objects.filter(
        device_id__in=RootAlias.physical_aliases(institution, device.id),
        lot__owner=institution,
    ).select_related("lot__type")
    outgoing = [dl.lot.created for dl in lots if lot_direction(dl.lot.type.name) == "outgoing"]
    if outgoing:
        signals.outgoing_since = min(outgoing)
    return signals


def _naive(d: datetime | None) -> datetime | None:
    return d.replace(tzinfo=None) if d is not None and d.tzinfo else d


def resolve_reuse(points: list[tuple[str, datetime | None]], signals: ReuseSignals) -> tuple[int | None, str | None]:
    """Index in the chronological timeline where the second life starts, and why."""
    uuids = [uuid for uuid, _ in points]
    for index, uuid in enumerate(uuids):
        if uuid in signals.marks:
            return index, SOURCE_MARK
    if signals.transfer_uuid in uuids:
        return uuids.index(signals.transfer_uuid), SOURCE_TRANSFER_STATE
    if signals.outgoing_since is not None and points:
        cutoff = _naive(signals.outgoing_since)
        before = [i for i, (_, date) in enumerate(points) if date is not None and _naive(date) <= cutoff]
        return (before[-1] if before else len(points) - 1), SOURCE_OUTGOING_LOT
    if len(points) >= 2 and not signals.end_of_life:
        return 0, SOURCE_SECOND_EVIDENCE
    return None, None


def resolve_reuse_start(ordered_uuids: list[str], marks: set[str]) -> tuple[int | None, str | None]:
    """Marks and second evidence only (kept for callers without states or lots)."""
    return resolve_reuse([(u, None) for u in ordered_uuids], ReuseSignals(marks=set(marks)))


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
