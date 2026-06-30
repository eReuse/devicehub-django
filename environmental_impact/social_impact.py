"""Social-impact (digital inclusion) calculation.

Counterweight to the environmental impact: pure environmental accounting always
favours recycling, because an old device keeps drawing power and pollutes more
than a current model. That view misses the *social* value of reuse, e.g. a
device used by a person who previously had no computer access (digital
inclusion). See ereuse/projectes#345.

Server-side, no new app, no workbench/Android change.

Model — per-evidence flag (generalises to many disjoint inclusion periods):

  A device's life is a chain of evidences (one per snapshot), each carrying
  power-on hours. The *span* between two consecutive evidences is either
  vulnerable-person use or not. An eReuse manager marks the spans that were; we
  store one ``social:inclusion_use`` :class:`~evidence.models.UserProperty` per
  marked evidence (keyed on that evidence's own uuid, so it survives later
  snapshots and never needs reconciling).

  This handles arbitrary lifecycles, e.g.
  refurbish -> inclusion -> sold back -> donated -> inclusion again: just two
  marked intervals, i.e. two runs of flagged spans. Digital-inclusion hours =
  sum of power-on-hours deltas over flagged spans only.

The start/end interval picker in the UI is only an input convenience: it is
expanded into per-span flags on save (and several intervals can be marked).

For now we only surface the inclusion hours. A scoring formula ("fórmula mínima
de impacto social") is still open (ereuse/projectes#345, Leandro); keep the
inputs explicit so it can be added later without touching storage or the view.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from evidence.models import Evidence, UserProperty
from .algorithms.common import get_poh_from_device, get_poh_from_evidence

if TYPE_CHECKING:
    from device.models import Device
    from user.models import Institution


# UserProperty keys, namespaced like the existing "usage:power_on_hours".
class SocialKeys:
    # Device-level gate: was the device ever used by a vulnerable person.
    VULNERABLE = "social:vulnerable_person"
    # Per-evidence: the span starting at this evidence was vulnerable-person use.
    INCLUSION_USE = "social:inclusion_use"


#: Values written for the boolean flags.
TRUE_VALUE = "yes"
FALSE_VALUE = "no"


class SocialImpact:
    """Result of a social-impact calculation (plain object, no DB model)."""

    def __init__(self):
        self.vulnerable_person: bool = False
        # Ordered evidence timeline: list of {"uuid", "date", "poh", "flagged"}.
        self.timeline: list = []
        # Evidence uuids whose following span is marked vulnerable-use.
        self.flagged_uuids: set = set()
        # Contiguous flagged periods for display: list of {"from", "to"} dates.
        self.intervals: list = []
        # Power-on hours over flagged spans (or total usage when vulnerable but
        # nothing marked). This is the reuse value environmental accounting
        # alone never credits.
        self.digital_inclusion_hours: int = 0
        self.relevant_input_data: dict = {}


def _bool_value(value: str | None) -> bool:
    return (value or "").strip().lower() in {TRUE_VALUE, "true", "1", "si", "sí"}


def read_vulnerable_flag(device: "Device", institution: "Institution") -> bool:
    """Latest device-level vulnerable-person gate across all evidences."""
    uuids = device.uuids or []
    if not uuids:
        return False
    prop = (
        UserProperty.objects.filter(
            uuid__in=uuids, owner=institution, key=SocialKeys.VULNERABLE
        )
        .order_by("-created")
        .first()
    )
    return _bool_value(prop.value) if prop else False


def read_flagged_uuids(device: "Device", institution: "Institution") -> set:
    """Set of evidence uuids marked as vulnerable-use spans."""
    uuids = device.uuids or []
    if not uuids:
        return set()
    rows = UserProperty.objects.filter(
        uuid__in=uuids,
        owner=institution,
        key=SocialKeys.INCLUSION_USE,
    ).values_list("uuid", "value")
    return {str(u) for u, v in rows if _bool_value(v)}


def evidence_timeline(device: "Device") -> list:
    """Ordered (oldest-first) evidence timeline with power-on hours.

    Each entry is ``{"uuid", "date", "poh"}``. One Xapian doc fetch per
    evidence; fine for the handful of snapshots a device has today, but worth
    caching if periodic snapshots make timelines long.
    """
    items = []
    for uuid in device.uuids or []:
        ev = Evidence(uuid)
        ev.get_doc()
        ev.get_time()
        items.append(
            {
                "uuid": str(uuid),
                "date": ev.created,
                "poh": get_poh_from_evidence(ev),
            }
        )
    items.sort(key=lambda x: x["date"] or "")
    return items


def inclusion_hours_from_flags(timeline: list, flagged_uuids: set) -> int:
    """Sum power-on-hours deltas over flagged spans only.

    A span is the gap between ``timeline[i]`` and ``timeline[i + 1]``; it counts
    when ``timeline[i]`` is flagged. Naturally unions multiple disjoint periods.
    """
    hours = 0
    for i in range(len(timeline) - 1):
        if timeline[i]["uuid"] in flagged_uuids:
            hours += max(0, timeline[i + 1]["poh"] - timeline[i]["poh"])
    return hours


def expand_intervals_to_flagged_uuids(timeline: list, intervals: list) -> set:
    """Expand (from_uuid, to_uuid) interval pairs into flagged span uuids.

    Flags every evidence from ``from`` up to (but excluding) ``to``; a missing
    or unknown ``to`` means "ongoing" -> up to the latest evidence. Multiple
    intervals union together, so overlapping marks are not double counted.
    """
    index = {item["uuid"]: i for i, item in enumerate(timeline)}
    n = len(timeline)
    flagged: set = set()
    for frm, to in intervals:
        if frm not in index:
            continue
        i0 = index[frm]
        i1 = index[to] if to in index else n - 1
        for span in range(i0, i1):  # spans i0 .. i1 - 1
            flagged.add(timeline[span]["uuid"])
    return flagged


def _flagged_intervals_for_display(timeline: list, flagged_uuids: set) -> list:
    """Collapse flagged spans into contiguous {"from", "to"} date ranges."""
    intervals = []
    start = None
    for i in range(len(timeline) - 1):
        is_flagged = timeline[i]["uuid"] in flagged_uuids
        if is_flagged and start is None:
            start = timeline[i]
        if not is_flagged and start is not None:
            intervals.append(
                {
                    "from": start["date"],
                    "to": timeline[i]["date"],
                    "from_uuid": start["uuid"],
                    "to_uuid": timeline[i]["uuid"],
                }
            )
            start = None
    if start is not None:
        intervals.append(
            {
                "from": start["date"],
                "to": timeline[-1]["date"],
                "from_uuid": start["uuid"],
                "to_uuid": timeline[-1]["uuid"],
            }
        )
    return intervals


def compute_device_social_impact(
    device: "Device", institution: "Institution"
) -> SocialImpact:
    """Compute the (provisional) digital-inclusion impact for a device."""
    impact = SocialImpact()
    impact.timeline = evidence_timeline(device)
    impact.vulnerable_person = read_vulnerable_flag(device, institution)
    impact.flagged_uuids = read_flagged_uuids(device, institution)

    usage_hours = get_poh_from_device(device)
    inclusion_hours = 0

    if impact.vulnerable_person:
        if impact.flagged_uuids:
            inclusion_hours = inclusion_hours_from_flags(
                impact.timeline, impact.flagged_uuids
            )
            impact.intervals = _flagged_intervals_for_display(
                impact.timeline, impact.flagged_uuids
            )
        else:
            # Vulnerable but no spans marked: credit the whole usage.
            inclusion_hours = usage_hours

    impact.digital_inclusion_hours = inclusion_hours

    impact.relevant_input_data = {
        "vulnerable_person": impact.vulnerable_person,
        "usage_hours": usage_hours,
        "inclusion_periods": len(impact.intervals),
    }
    return impact
