"""What the three lot views draw from an ereuse2026 ``LotImpact``.

* refurbisher: the operator's own view of the lot;
* supplier: for whoever handed the devices over (donation or purchase);
* recipient: for whoever received them (sale or donation).

Every lot can show all three; the lot's tag only picks the one that opens first.
"""

from __future__ import annotations

from statistics import median

from django.utils.translation import gettext_lazy as _, ngettext

from environmental_impact.algorithms.ereuse2026.model import DeviceImpact, LotImpact
from environmental_impact.algorithms.ereuse2026.ereuse2026 import load_factors
from environmental_impact.presenters import ITU_STAGE, round_km
from environmental_impact.reuse import lot_direction

VIEWS = ("refurbisher", "supplier", "recipient")
DEFAULT_VIEW = {"incoming": "supplier", "outgoing": "recipient"}

STAGES = [
    ("manufacture", _("Manufacture"), _("raw material and production")),
    ("transport", _("Transport"), _("all legs")),
    ("use1", _("Use, life 1"), _("first owners")),
    ("refurbish", _("Refurbish"), _("not modelled")),
    ("use2", _("Use, life 2"), _("second users")),
    ("end_of_life", _("End of life"), _("recycling credit")),
]


def default_view(tag_name: str | None) -> str:
    return DEFAULT_VIEW.get(lot_direction(tag_name), "refurbisher")


def kg(value: float | None) -> str:
    """kg below a tonne, t above; used inside generated sentences."""
    if value is None:
        return "—"
    if abs(value) >= 1000:
        return f"{value / 1000:,.1f} t"
    return f"{value:,.0f} kg"


def _pct(value: float, largest: float) -> float:
    if not largest:
        return 0.0
    return round(max(0.0, min(100.0, 100 * value / largest)), 2)


def _legs(d: DeviceImpact) -> float:
    """Refurbisher van legs = transport stage minus the new device's own transport."""
    new_transport = d.new_equivalent_kg - d.stages["manufacture"]
    return max(0.0, d.stages["transport"] - new_transport)


def _row(device, d: DeviceImpact) -> dict:
    name = " ".join(x for x in (device.manufacturer, device.model) if x) if device else ""
    return {
        "id": device.id if device else "",
        "shortid": getattr(device, "shortid", "") or "",
        "name": name or _("Unknown model"),
        "type": d.device_type,
        "status": d.status,
        "ended": d.second_life_ended,
        "reuse_source": d.reuse_source,
        "life1": d.life1_hours,
        "life1_measured": d.life1_measured,
        "hours_estimated": d.hours_estimated,
        "life2": d.life2_hours if d.reused else None,
        "life2_measured": d.life2_measured,
        "unused_percent": round(100 * d.unused_share) if d.unused_share is not None else None,
        "apos_percent": round(100 * d.apos_share) if d.apos_share is not None else None,
        "avoided": d.avoided,
        "attributed": d.attributed_kg,
        "new_equivalent": d.new_equivalent_kg,
        "kwh_per_year": d.kwh_per_year,
        "hours_per_year_measured": d.hours_per_year_measured,
    }


def _sources(factors: dict) -> list[dict]:
    """Numbered notes behind the refurbisher tiles, with full citations from factors.json."""
    src = factors["sources"]
    car, tech = factors["car_kgco2e_per_km"], factors["technician_hours"]

    def cite(*keys):
        return [src[k] for k in keys]

    return [
        {"n": 1, "label": _("Car equivalence"),
         "detail": f"{car['value']} kg CO₂e/km. {car['ref']}.", "refs": cite("base_carbone")},
        {"n": 2, "label": _("Avoided emissions"),
         "detail": _("Compared with giving the same people new devices. The headline uses the public ADEME "
                     "Base Carbone factors; the range uses manufacturer data (Boavizta p10–p90)."),
         "refs": cite("base_carbone", "boavizta")},
        {"n": 3, "label": _("Technician work"),
         "detail": _("Estimate per device: %(rd)s h per desktop and %(rl)s h per laptop refurbished, "
                     "%(cd)s h and %(cl)s h prepared for recycling. %(ref)s.")
         % {"rd": f"{tech['reuse']['desktop']:g}", "rl": f"{tech['reuse']['laptop']:g}",
            "cd": f"{tech['recycle']['desktop']:g}", "cl": f"{tech['recycle']['laptop']:g}", "ref": tech["ref"]},
         "refs": cite("thesis")},
    ]


def lot_impact_view(lot: LotImpact, rows: list[tuple[object, DeviceImpact]], tag_name: str | None,
                    view: str | None, prepared_for: str, lot_name: str, inclusion: dict | None = None) -> dict:
    """``inclusion`` ({"people": n, "hours": h}, from the vulnerable-person marks) is sensitive:
    it is only passed on to the refurbisher view, never to reports that leave the organisation."""
    view = view if view in VIEWS else default_view(tag_name)
    impacts = [d for _, d in rows]
    reused = [d for d in impacts if d.reused]

    # scenarios (reused devices)
    scenario_max = max(lot.s1, lot.s2, lot.s3) or 1.0
    scenarios = [
        {"key": "S1", "label": _("Recycle only"), "value": lot.s1, "served": _("donors only"), "highlight": False},
        {"key": "S2", "label": _("Reuse (this lot)"), "value": lot.s2, "served": lot.reused, "highlight": True},
        {"key": "S3", "label": _("New devices"), "value": lot.s3, "served": lot.reused, "highlight": False},
    ]
    # per hour of use (paper §3, p.4): S1 serves the donors only, S2 and S3 donors and second users
    hours_s1 = sum(d.life1_hours + d.life2_hours for d in reused)
    hours_s23 = sum(d.life1_hours + 2 * d.life2_hours for d in reused)
    for s in scenarios:
        s["width"] = _pct(s["value"], scenario_max)
        s["text"] = kg(s["value"])
        hours = hours_s1 if s["key"] == "S1" else hours_s23
        s["g_per_hour"] = round(1000 * s["value"] / hours) if hours else None

    # what giving the second users a computer added, over recycling (which gives them nothing)
    giving = [
        {"label": _("Refurbished"), "value": lot.cost_second_users, "text": kg(lot.cost_second_users),
         "width": _pct(lot.cost_second_users, lot.cost_with_new), "highlight": True},
        {"label": _("New"), "value": lot.cost_with_new, "text": kg(lot.cost_with_new),
         "width": 100.0 if lot.cost_with_new else 0.0, "highlight": False},
    ]

    # stages: positive bars share one scale, the recycling credit is drawn below zero
    stage_values = [(k, label, note, lot.stages.get(k, 0.0)) for k, label, note in STAGES]
    positive_max = max((v for *_, v in stage_values if v > 0), default=1.0)
    negative_max = max((-v for *_, v in stage_values if v < 0), default=0.0)
    span = positive_max + negative_max or 1.0
    stages = [
        {"key": k, "label": label, "note": note, "itu": ITU_STAGE[k], "value": v, "text": kg(v) if v else "—",
         "up": _pct(max(v, 0), span), "down": _pct(max(-v, 0), span)}
        for k, label, note, v in stage_values
    ]

    measured_life1 = [d.life1_hours for d in impacts if d.life1_measured]
    device_rows = sorted((_row(dev, d) for dev, d in rows), key=lambda r: (r["status"] != "reused", -(r["avoided"] or 0)))
    grids = sorted({d.country for d in impacts})
    legs_total = sum(_legs(d) for d in reused)

    supplier_ok = [
        ngettext("In this lot we handed over %(n)s device. ", "In this lot we handed over %(n)s devices. ",
                 lot.devices) % {"n": lot.devices}
        + ngettext("%(r)s was refurbished and reused", "%(r)s were refurbished and reused",
                   lot.reused) % {"r": lot.reused}
        + (_(", contributing to avoiding at least %(a)s CO₂e compared with providing new ones "
             "(%(lo)s–%(hi)s with manufacturer data).")
           if lot.avoided and lot.avoided_low and lot.avoided < lot.avoided_low else
           _(", contributing to avoiding an estimated %(a)s CO₂e compared with providing new ones "
             "(%(lo)s–%(hi)s with manufacturer data)."))
        % {"a": kg(lot.avoided), "lo": kg(lot.avoided_low), "hi": kg(lot.avoided_high)},
    ]
    if lot.recycled:
        supplier_ok.append(ngettext(
            "%(n)s device was sent to recycling.", "%(n)s devices were sent to recycling.", lot.recycled
        ) % {"n": lot.recycled})
    # only hours read from later scans are reported; projected second lives stay in the calculation
    hours_measured = lot.life2_hours_measured
    awaiting_scan = sum(1 for d in reused if not d.life2_measured)
    if lot.reused and hours_measured:
        supplier_ok.append(ngettext(
            "The reused devices gave %(n)s person a computer, with %(h)s hours of use measured so far.",
            "The reused devices gave %(n)s people a computer, with %(h)s hours of use measured so far.",
            lot.reused,
        ) % {"n": lot.reused, "h": f"{hours_measured:,.0f}"})
    elif lot.reused:
        supplier_ok.append(ngettext(
            "The reused devices gave %(n)s person a computer.",
            "The reused devices gave %(n)s people a computer.",
            lot.reused,
        ) % {"n": lot.reused})
    social_no = _("“We closed the digital divide” or “we transformed lives”: hours of use show access, not impact.")
    supplier_no = [
        _("“We reduced our carbon footprint by %(a)s.” Avoided emissions are not a reduction of your own footprint.")
        % {"a": kg(lot.avoided)},
        _("“Carbon neutral”, “climate positive”, “offset” or “eco-friendly IT”."),
        _("Adding these figures to your Scope 1, 2 or 3 totals, or claiming them as yours alone."),
        social_no,
    ]
    recipient_ok = [
        ngettext(
            "Our %(n)s refurbished device carries an estimated %(a)s CO₂e of embodied emissions, against "
            "about %(new)s for a new equivalent (manufacturing split between owners by hours of use, APOS).",
            "Our %(n)s refurbished devices carry an estimated %(a)s CO₂e of embodied emissions, against "
            "about %(new)s for new equivalents (manufacturing split between owners by hours of use, APOS).",
            lot.reused,
        )
        % {"n": lot.reused, "a": kg(lot.attributed_kg), "new": kg(lot.new_equivalent_kg)},
    ]
    recipient_no = [
        _("“Zero-emission” or “carbon-neutral” devices: refurbished devices still carry emissions and use electricity."),
        _("Claiming the supplier's or refurbisher's avoided emissions as your own reduction."),
        _("Mixing allocation methods between years. A stricter cut-off method (only the refurbisher's transport) "
          "would give %(cut)s; check with your auditor which one you report and keep it.") % {"cut": kg(legs_total)},
        social_no,
    ]

    return {
        "view": view,
        "direction": lot_direction(tag_name),
        "tag_name": tag_name,
        "lot_name": lot_name,
        "prepared_for": prepared_for,
        "lot": lot,
        "grids": grids,
        "avoided_text": kg(lot.avoided),
        # avoided emissions in everyday terms, same factor and rounding as the device tab
        "avoided_car_km": round_km(lot.avoided / load_factors()["car_kgco2e_per_km"]["value"])
        if lot.avoided and lot.avoided > 0 else None,
        "avoided_low_text": kg(lot.avoided_low),
        "avoided_high_text": kg(lot.avoided_high),
        "cost_reuse_text": kg(lot.cost_second_users),
        "cost_new_text": kg(lot.cost_with_new),
        "hours_measured": hours_measured,
        "awaiting_scan": awaiting_scan,
        "scanned_again": lot.reused - awaiting_scan,
        # social value (thesis §6.4 p.105; paper §3.2 p.3): access, local work, and the carbon cost of access
        "cost_per_person_reuse_text": kg(lot.cost_second_users / lot.reused) if lot.reused else None,
        "cost_per_person_new_text": kg(lot.cost_with_new / lot.reused) if lot.reused else None,
        "inclusion": inclusion if view == "refurbisher" else None,
        "scenarios": scenarios,
        "giving": giving,
        # a constant per device type (thesis Table 13, p.115, Solidança estimates), not a measurement
        "technician_rates": load_factors()["technician_hours"],
        "sources": _sources(load_factors()),
        # the public ADEME factor can sit below every manufacturer figure: then it is a floor, "at least"
        "avoided_below_range": bool(lot.avoided and lot.avoided_low and lot.avoided < lot.avoided_low),
        "stages": stages,
        "stages_total_text": kg(sum(lot.stages.values())),
        "transport_text": kg(lot.stages.get("transport", 0.0)),
        "rows": device_rows,
        # what the refurbisher can do: scan these devices
        "rows_awaiting_scan": [r for r in device_rows if r["status"] == "reused" and not r["life2_measured"]],
        "rows_missing_life1": [r for r in device_rows if not r["life1_measured"]],
        "median_life1": median(measured_life1) if measured_life1 else None,
        "missing_life1": lot.devices - lot.devices_with_life1_reading,
        "attributed_text": kg(lot.attributed_kg),
        "new_equivalent_text": kg(lot.new_equivalent_kg),
        "attributed_saving_percent": round(100 * (1 - lot.attributed_kg / lot.new_equivalent_kg)) if lot.new_equivalent_kg else None,
        "recipient_bars": [
            {"label": _("These refurbished devices"), "value": lot.attributed_kg, "text": kg(lot.attributed_kg),
             "width": _pct(lot.attributed_kg, lot.new_equivalent_kg), "highlight": True},
            {"label": _("Same number of new ones"), "value": lot.new_equivalent_kg, "text": kg(lot.new_equivalent_kg),
             "width": 100.0 if lot.new_equivalent_kg else 0.0, "highlight": False},
        ],
        "supplier_ok": supplier_ok,
        "supplier_no": supplier_no,
        "recipient_ok": recipient_ok,
        "recipient_no": recipient_no,
    }
