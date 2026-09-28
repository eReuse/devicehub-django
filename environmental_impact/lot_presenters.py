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
from environmental_impact.presenters import ITU_STAGE
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
    for s in scenarios:
        s["width"] = _pct(s["value"], scenario_max)
        s["text"] = kg(s["value"])

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
    grids = sorted({d.country for d in impacts})
    legs_total = sum(_legs(d) for d in reused)

    supplier_ok = [
        ngettext("In this lot we handed over %(n)s device. ", "In this lot we handed over %(n)s devices. ",
                 lot.devices) % {"n": lot.devices}
        + ngettext("%(r)s was refurbished and reused", "%(r)s were refurbished and reused",
                   lot.reused) % {"r": lot.reused}
        + _(", contributing to avoiding an estimated %(a)s CO₂e compared with providing new ones (range %(lo)s–%(hi)s).")
        % {"a": kg(lot.avoided), "lo": kg(lot.avoided_low), "hi": kg(lot.avoided_high)},
    ]
    if lot.recycled:
        supplier_ok.append(ngettext(
            "%(n)s device was sent to recycling.", "%(n)s devices were sent to recycling.", lot.recycled
        ) % {"n": lot.recycled})
    access_hours = lot.life2_hours_measured + lot.life2_hours_projected
    if lot.reused:
        supplier_ok.append(ngettext(
            "The reused devices gave %(n)s person a computer, for about %(h)s hours of use (measured and projected).",
            "The reused devices gave %(n)s people a computer, for about %(h)s hours of use (measured and projected).",
            lot.reused,
        ) % {"n": lot.reused, "h": f"{access_hours:,.0f}"})
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
            "Our %(n)s refurbished device carries an estimated %(a)s CO₂e of embodied emissions (APOS "
            "allocation by hours of use, Roura et al. 2026), against about %(new)s for a new equivalent.",
            "Our %(n)s refurbished devices carry an estimated %(a)s CO₂e of embodied emissions (APOS "
            "allocation by hours of use, Roura et al. 2026), against about %(new)s for new equivalents.",
            lot.reused,
        )
        % {"n": lot.reused, "a": kg(lot.attributed_kg), "new": kg(lot.new_equivalent_kg)},
        _("Their electricity use is estimated at %(kwh)s kWh per year (%(kg)s CO₂e).")
        % {"kwh": f"{lot.kwh_per_year:,.0f}", "kg": kg(lot.kg_per_year)},
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
        "avoided_low_text": kg(lot.avoided_low),
        "avoided_high_text": kg(lot.avoided_high),
        "cost_reuse_text": kg(lot.cost_second_users),
        "cost_new_text": kg(lot.cost_with_new),
        "hours_total": access_hours,
        # social value (thesis §6.4 p.105; paper §3.2 p.3): access, local work, and the carbon cost of access
        "cost_per_person_reuse_text": kg(lot.cost_second_users / lot.reused) if lot.reused else None,
        "cost_per_person_new_text": kg(lot.cost_with_new / lot.reused) if lot.reused else None,
        "inclusion": inclusion if view == "refurbisher" else None,
        "scenarios": scenarios,
        "stages": stages,
        "stages_total_text": kg(sum(lot.stages.values())),
        "transport_text": kg(lot.stages.get("transport", 0.0)),
        "rows": sorted((_row(dev, d) for dev, d in rows), key=lambda r: (r["status"] != "reused", -(r["avoided"] or 0))),
        "median_life1": median(measured_life1) if measured_life1 else None,
        "unused_text": kg(lot.unused_kg),
        "unused_carried_text": kg(lot.unused_kg_carried),
        "missing_life1": lot.devices - lot.devices_with_life1_reading,
        "measured_hours_percent": (
            round(100 * lot.life2_hours_measured / (lot.life2_hours_measured + lot.life2_hours_projected))
            if (lot.life2_hours_measured + lot.life2_hours_projected) else None
        ),
        "unused_lost_text": kg(lot.unused_kg_lost),
        "attributed_text": kg(lot.attributed_kg),
        "new_equivalent_text": kg(lot.new_equivalent_kg),
        "attributed_saving_percent": round(100 * (1 - lot.attributed_kg / lot.new_equivalent_kg)) if lot.new_equivalent_kg else None,
        "kg_per_year_text": kg(lot.kg_per_year),
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
