"""Turn an ereuse2026 ``DeviceImpact`` into what the device tab draws.

Every number and bar width is computed here so the template only prints values
and sets CSS widths. Widths are percentages of the widest value in each chart.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from environmental_impact.algorithms.ereuse2026.ereuse2026 import load_factors
from environmental_impact.algorithms.ereuse2026.model import DeviceImpact, DeviceInputs

STAGE_LABELS = [
    ("manufacture", _("Manufacture")),
    ("transport", _("Transport")),
    ("use1", _("Use, life 1")),
    ("refurbish", _("Refurbish")),
    ("use2", _("Use, life 2")),
    ("end_of_life", _("End of life")),
]


PROVENANCE_LABELS = {
    "life1_hours": _("Life 1 hours"),
    "life2_hours": _("Life 2 hours"),
    "manufacturing": _("New device footprint"),
    "grid": _("Electricity grid"),
    "bios_year": _("Manufacture year"),
    "reuse_start": _("Reuse start"),
}


REUSE_SOURCE_LABELS = {
    "mark": _("Marked by hand"),
    "transfer_state": _("Transfer state"),
    "outgoing_lot": _("Outgoing lot"),
    "second_evidence": _("Second evidence"),
}


def _nice_step(raw: float) -> int:
    """A round tick step (1, 2 or 5 × a power of ten) near ``raw``."""
    if raw <= 0:
        return 1
    power = 10 ** (len(str(int(raw))) - 1) if raw >= 1 else 1
    return min((m * power for m in (1, 2, 5, 10)), key=lambda step: abs(step - raw))


def _pct(value: float, largest: float) -> float:
    if not largest:
        return 0.0
    return round(max(0.0, min(100.0, 100 * value / largest)), 2)


def device_impact_view(impact: DeviceImpact, inputs: DeviceInputs, marks: set[str]) -> dict:
    factors = load_factors()
    typical = factors["typical_first_life_hours"][impact.device_type]
    h1, h2 = impact.life1_hours, impact.life2_hours if impact.reused else 0
    story_max = max(typical, h1 + h2)
    story_step = _nice_step(story_max / 4)
    story_ticks = [
        {"hours": t, "left": _pct(t, story_max)}
        for t in range(0, int(story_max) + 1, story_step)
    ]
    life1_point = inputs.points[inputs.reuse_start] if impact.reused else inputs.points[-1]

    per_hour = [{"label": _("Life 1 only"), "value": impact.g_per_hour_life1, "highlight": False}]
    if impact.reused and impact.g_per_hour_total is not None:
        per_hour.append({"label": _("With its second life"), "value": impact.g_per_hour_total, "highlight": True})
    per_hour_max = max(row["value"] for row in per_hour)
    for row in per_hour:
        row["width"] = _pct(row["value"], per_hour_max)
    per_hour_drop = None
    per_hour_rise_cause = None
    if len(per_hour) == 2 and per_hour[0]["value"]:
        per_hour_drop = round(100 * (1 - per_hour[1]["value"] / per_hour[0]["value"]))
        if per_hour_drop <= 0:
            # The second life adds the refurbisher's van legs plus its own electricity.
            # Name whichever of the two outweighs the other, instead of assuming one.
            new_transport = impact.new_equivalent_kg - impact.stages["manufacture"]
            legs = max(0.0, impact.stages["transport"] - new_transport)
            per_hour_rise_cause = "transport" if legs >= impact.stages["use2"] else "electricity"

    divisor = impact.lifetime_years or 1.0
    stages = [
        {"key": key, "label": label, "value": impact.stages.get(key, 0.0) / divisor}
        for key, label in STAGE_LABELS
    ]
    stage_max = max(s["value"] for s in stages) or 1.0
    for s in stages:
        s["height"] = _pct(s["value"], stage_max)

    timeline = [
        {
            "uuid": p.uuid,
            "date": p.date,
            "poh": p.poh,
            "disk_changed": p.disk_changed,
            "marked": p.uuid in marks,
            "is_start": impact.reused and inputs.reuse_start == i,
        }
        for i, p in enumerate(inputs.points)
    ]

    provenance = [
        {
            "label": PROVENANCE_LABELS.get(p.key, p.key),
            "value": REUSE_SOURCE_LABELS.get(p.value, p.value) if p.key == "reuse_start" else p.value,
            "measured": p.measured,
            "source": p.source,
        }
        for p in impact.provenance
    ]

    return {
        "impact": impact,
        "provenance": provenance,
        "reused": impact.reused,
        "is_mobile": impact.device_type in ("smartphone", "tablet"),
        "story": {
            "life1_width": _pct(h1, story_max),
            "life2_width": _pct(h2, story_max),
            "typical_width": _pct(typical, story_max),
            "typical_hours": typical,
            "total_hours": h1 + h2,
            "ticks": story_ticks,
            # the evidence whose counter gives the life-1 hours (intake, or the latest scan if pending)
            "life1_date": life1_point.date,
            "intake": inputs.points[inputs.reuse_start].date if impact.reused else None,
            "life2_years": factors["default_second_life"][impact.device_type]["years"],
        },
        "per_hour": per_hour,
        "per_hour_drop": per_hour_drop,
        "per_hour_rise_cause": per_hour_rise_cause,
        "stages": stages,
        "stages_per_year": bool(impact.lifetime_years),
        "stages_total": impact.total_kg,
        "unused_percent": round(100 * impact.unused_share) if impact.unused_share is not None else None,
        "apos_percent": round(100 * impact.apos_share) if impact.apos_share is not None else None,
        "expected_life2_hours": factors["default_second_life"][impact.device_type]["hours"],
        "timeline": timeline,
        "has_mark": bool(marks),
        "bios_year": inputs.bios_year,
        "factor_label": factors["manufacturing"][impact.factor_set]["label"],
    }
