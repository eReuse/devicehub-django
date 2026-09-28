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


DEVICE_INPUT_KEYS = ("life1_hours", "life2_hours", "bios_year", "reuse_start")

# Manufacturing factor set → entry in factors["sources"]
FACTOR_SET_SOURCES = {
    "base_carbone": "base_carbone",
    "boavizta_median": "boavizta",
    "ademe_arcep_2025": "ademe_arcep_2025",
}


def _method(impact: DeviceImpact, factors: dict) -> dict:
    """Every constant behind the device's figures, with numbered references.

    References are numbered in order of first use, so the list under the table
    only holds the sources this device actually relies on.
    """
    sources, numbers, references = factors["sources"], {}, []

    def cite(*keys):
        for key in keys:
            if key not in numbers:
                numbers[key] = len(numbers) + 1
                references.append({"n": numbers[key], **sources[key]})
        return [numbers[key] for key in keys]

    t = impact.device_type
    mobile = t in ("smartphone", "tablet")
    mf = factors["manufacturing"][impact.factor_set][t]
    power = factors["power_kw"][t]
    rows = []

    def row(label, value, where, *keys):
        rows.append({"label": label, "value": value, "where": where, "refs": cite(*keys)})

    row(_("New device, making and shipping"), f"{impact.new_equivalent_kg:.1f} kg CO₂e",
        mf["ref"], FACTOR_SET_SOURCES.get(impact.factor_set, "base_carbone"))
    if mobile:
        row(_("Electricity use"), f"{power['kwh_per_year']} kWh / year", power["ref"], "boavizta", "devicehub_estimator")
    else:
        sleep = factors["sleep_share"]["value"]
        row(_("Power drawn"), f"{power['idle'] * 1000:g} W on · {power['sleep'] * 1000:g} W asleep "
            f"({100 * sleep:.1f}% of the time)", _("idle power used for all time on"), "energy_star")
    grid_to = impact.grid_life2 if impact.reused else impact.grid_now
    row(_("Electricity grid"), f"{impact.grid_life1:.3f} → {grid_to:.3f} kg CO₂e/kWh ({impact.country})",
        _("yearly carbon intensity by country"), "owid")
    window = factors["first_life_grid_window_years"]
    row(_("Grid years for life 1"), f"{window['value']} " + str(_("years before intake")), window["ref"], "thesis")
    typical = factors["typical_first_life_hours"]
    if mobile:
        row(_("Typical first life"), f"{typical[t]:,} h", typical["mobile_ref"], "ademe_refurb_2022")
    else:
        row(_("Typical first life"), f"{typical[t]:,} h", typical["ref"], "franquesa_2019a", "thesis")
    second = factors["default_second_life"]
    if mobile:
        row(_("Expected second life"), f"{second[t]['hours']:,} h ({second[t]['years']} y)",
            second["mobile_ref"], "itu_l1410", "ademe_refurb_2022")
    else:
        row(_("Expected second life"), f"{second[t]['hours']:,} h ({second[t]['years']} y)", second["ref"], "thesis")
    min_h1 = factors["min_valid_life1_hours"]
    row(_("Shortest usable life-1 reading"), f"{min_h1['value']} h", min_h1["ref"], "thesis")
    weight = factors["weight_kg"]
    if mobile:
        row(_("Weight"), f"{weight[t]} kg", weight["mobile_ref"], "boavizta")
    else:
        row(_("Weight"), f"{weight[t]} kg", weight["ref"], "thesis")
    legs = factors["refurbisher_legs_km"]
    row(_("Van trips via the refurbisher"), f"{legs['value']} km", legs["ref"], "thesis")
    van = factors["van_kgco2e_per_tkm"]
    row(_("Van emissions"), f"{van['value']} kg CO₂e / t·km", van["ref"], "base_carbone")
    credit = factors["recycling_credit_kg"]
    if mobile:
        row(_("Recycling credit"), "0 kg", _("no published value for phones or tablets"), "thesis")
    else:
        row(_("Recycling credit"), f"{credit[t]} kg CO₂e", credit["ref"], "karpagam_2017", "thesis")
    row(_("Allocation between owners"), "APOS", _("§3.3, p.4: burden split by powered-on hours"), "paper")
    return {"constants": rows, "references": references}


DETECTED_REASONS = {
    "second_evidence": _("detected: there is a later scan"),
    "transfer_state": _("detected: its transfer state (e.g. DONATION)"),
    "outgoing_lot": _("detected: it went into an outgoing lot"),
}


def _handover(impact: DeviceImpact, inputs: DeviceInputs, timeline: list[dict]) -> dict:
    """Which scan the device was handed over at, and why: shown as an answer, corrected on demand."""
    points = inputs.points
    # a mark on the scan the rules pick anyway changes nothing: show the detected reason
    by_hand = (
        impact.reused and inputs.reuse_source == "mark" and inputs.reuse_start != inputs.detected_start
    )
    if impact.reused:
        source = inputs.detected_source if inputs.reuse_source == "mark" and not by_hand else inputs.reuse_source
        note = _("set by hand") if by_hand else DETECTED_REASONS.get(source, "")
    elif inputs.end_of_life:
        note = _("its latest state sends it to recycling")
    elif len(points) == 1:
        note = _("only one scan")
    else:
        note = ""
    # the scan pre-selected when correcting: the current start, else the latest scan
    selected = inputs.reuse_start if impact.reused else len(points) - 1
    return {
        "scan": timeline[inputs.reuse_start] if impact.reused else None,
        "note": note,
        "by_hand": by_hand,
        "single": len(points) == 1,
        "last": timeline[-1],
        "selected_uuid": timeline[selected]["uuid"],
    }


def device_impact_view(impact: DeviceImpact, inputs: DeviceInputs, marks: set[str]) -> dict:
    factors = load_factors()
    typical = factors["typical_first_life_hours"][impact.device_type]
    # the story only draws hours read from the device; an estimated life 2 stays in the calculation
    h1 = impact.life1_hours
    h2 = impact.life2_hours if impact.reused and impact.life2_measured else 0
    story_max = max(typical, h1 + h2)
    story_step = _nice_step(story_max / 4)
    story_ticks = [
        {"hours": t, "left": _pct(t, story_max)}
        for t in range(0, int(story_max) + 1, story_step)
    ]
    life1_point = inputs.points[inputs.reuse_start] if impact.reused else inputs.points[-1]

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
            "has_reading": bool(p.poh),  # a counter at 0 means no reading, not zero hours
            "disk_changed": p.disk_changed,
            "marked": p.uuid in marks,
            "is_start": impact.reused and inputs.reuse_start == i,
            "detected": inputs.detected_start == i,
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
        if p.key in DEVICE_INPUT_KEYS
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
        "stages": stages,
        "stages_per_year": bool(impact.lifetime_years),
        "stages_total": impact.total_kg,
        "unused_percent": round(100 * impact.unused_share) if impact.unused_share is not None else None,
        "apos_percent": round(100 * impact.apos_share) if impact.apos_share is not None else None,
        "expected_life2_hours": factors["default_second_life"][impact.device_type]["hours"],
        "timeline": timeline,
        "has_mark": bool(marks),
        "handover": _handover(impact, inputs, timeline),
        "bios_year": inputs.bios_year,
        "factor_label": factors["manufacturing"][impact.factor_set]["label"],
        "method": _method(impact, factors),
    }
