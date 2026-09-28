"""eReuse 2026 impact model: pure calculation, no Django.

One device goes in as its evidence timeline (power-on hours per scan) plus a
few facts (type, BIOS year, country, where reuse starts); one ``DeviceImpact``
comes out. ``aggregate_lot`` sums devices for the lot views.

The model combines two lenses, both from the sources in
``~/ereuse/impacto_ambiental/agent`` (see ``docs.md``):

* **Consequential** (Roura Salietti 2025, ch. 6): scenarios S1 (recycle, the
  first user buys new, nobody else served), S2 (reuse) and S3 (new devices
  for both users). ``avoided = S3 - S2`` is what reuse avoided compared with
  giving the second user a new computer; ``cost_second_user = S2 - S1`` is
  what serving that user cost. Old and new devices are assumed to draw the
  same power, as in the thesis, so use-phase terms cancel in ``avoided``.
* **Attributional**: the device's own life-cycle stages (ITU-T L.1410 A-D)
  and what its second user carries. That share follows the APOS allocation
  stated in Roura et al. (2026, p.4): the old device's production and
  transport are split between users by the hours each gets, fixed at handover
  with the expected second-life hours. The ITU-T L.1410 App. XV / ADEME
  depreciation ("unused compared with a typical first life") is kept as
  ``unused_share`` for the supplier report's advice to hand devices over earlier.

All masses are kg CO2e, energy kWh, time powered-on hours unless named
otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from statistics import mean

METHOD_VERSION = "ereuse2026-v0"

SUPPORTED_TYPES = ("desktop", "laptop", "smartphone", "tablet")

HOURS_COUNTER = "counter"  # disk power-on counter (Workbench)
HOURS_ANDROID_ESTIMATE = "android_estimate"  # estimated from Android wear signals


class UnsupportedDevice(ValueError):
    """The device type has no complete factor set in this method version."""


@dataclass
class EvidencePoint:
    uuid: str
    date: datetime | None
    poh: int
    # The storage device differs from the previous evidence, so the hours
    # between the two cannot be measured from power-on counters.
    disk_changed: bool = False


@dataclass
class DeviceInputs:
    device_type: str  # "desktop" | "laptop"
    points: list[EvidencePoint]
    country: str
    reuse_start: int | None = None  # index in ``points`` where the second life starts
    reuse_source: str | None = None  # "mark" | "second_evidence"
    bios_year: int | None = None
    factor_set: str = "base_carbone"
    hours_method: str = HOURS_COUNTER
    # Latest state says the device went to recycling (disposition recycled/disposed).
    end_of_life: bool = False


@dataclass
class Provenance:
    key: str
    value: str
    measured: bool
    source: str


@dataclass
class DeviceImpact:
    method_version: str
    device_type: str
    status: str  # "reused" | "pending" | "recycled"
    reuse_source: str | None
    factor_set: str
    country: str
    # hours
    life1_hours: int
    life1_measured: bool
    # Phones: hours come from the Android estimator, not a counter.
    hours_estimated: bool = False
    life2_hours: int = 0
    life2_measured: bool = False
    life2_disk_swaps: int = 0
    # grid, kg CO2e/kWh
    grid_life1: float = 0.0
    grid_life2: float = 0.0
    grid_now: float = 0.0
    # device's own life-cycle, by L.1410 stage
    stages: dict = field(default_factory=dict)
    # scenarios (reused devices only)
    s1: float | None = None
    s2: float | None = None
    s3: float | None = None
    avoided: float | None = None
    avoided_low: float | None = None
    avoided_high: float | None = None
    cost_second_user: float | None = None
    # current owner's view (ITU L.1410 App. XV)
    # ITU L.1410 App. XV / ADEME: manufacturing still unused vs a typical first life
    unused_share: float | None = None
    unused_kg: float | None = None
    # APOS (Roura et al. 2026): second user's share of the old device's production + transport
    apos_share: float | None = None
    passed_on_kg: float | None = None  # apos_share × (manufacturing + transport)
    attributed_kg: float | None = None  # passed_on_kg + refurbisher legs
    new_equivalent_kg: float = 0.0
    # per hour of use, g CO2e
    g_per_hour_life1: float | None = None
    g_per_hour_total: float | None = None
    # running it
    hours_per_year: float | None = None
    hours_per_year_measured: bool = False
    kwh_per_year: float | None = None
    kg_per_year: float | None = None
    # calendar life, for the per-year ITU view
    lifetime_years: float | None = None
    # A reused device that has since gone to recycling: its second life is over.
    second_life_ended: bool = False
    technician_hours: float | None = 0.0  # None: no source for this device type
    provenance: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def reused(self) -> bool:
        return self.status == "reused"

    @property
    def recycled(self) -> bool:
        return self.status == "recycled"

    @property
    def total_kg(self) -> float:
        return sum(self.stages.values())

    @property
    def use_phase_kg(self) -> float:
        return self.stages.get("use1", 0.0) + self.stages.get("use2", 0.0)


# --------------------------------------------------------------------------- grid


class GridSeries:
    """Carbon intensity of electricity per country and year (kg CO2e/kWh)."""

    def __init__(self, series: dict, latest: dict | None = None, default_country: str = "ES"):
        self.series = {
            code: {int(year): float(value) for year, value in years.items()}
            for code, years in series.items()
        }
        # Countries missing from the series fall back to a flat latest value (g/kWh in the old file).
        self.latest = {code: float(v) / 1000 for code, v in (latest or {}).items()}
        self.default_country = default_country

    def resolve(self, country: str | None) -> tuple[str, str | None]:
        code = (country or self.default_country).upper()
        if code in self.series or code in self.latest:
            return code, None
        return self.default_country, (
            f"Unknown country code '{code}'. Using {self.default_country} grid."
        )

    def at(self, country: str, year: int) -> float:
        years = self.series.get(country)
        if not years:
            return self.latest[country]
        first, last = min(years), max(years)
        return years[min(last, max(first, year))]

    def mean(self, country: str, first_year: int, last_year: int) -> float:
        return mean(self.at(country, y) for y in range(first_year, last_year + 1))

    def latest_year(self, country: str) -> int | None:
        years = self.series.get(country)
        return max(years) if years else None


# -------------------------------------------------------------------------- model


def _year_fraction(d: datetime) -> float:
    return d.year + (d.month - 0.5) / 12


def _span_hours(points: list[EvidencePoint], start: int) -> tuple[int, bool, int]:
    """Hours over the spans after ``start``; skips spans with a disk swap.

    Returns (hours, any_span_measured, disk_swaps).
    """
    hours, measured, swaps = 0, False, 0
    for j in range(start, len(points) - 1):
        nxt = points[j + 1]
        if nxt.disk_changed:
            swaps += 1
            continue
        hours += max(0, nxt.poh - points[j].poh)
        measured = True
    return hours, measured, swaps


def compute_device(inputs: DeviceInputs, factors: dict, grid: GridSeries) -> DeviceImpact:
    t = inputs.device_type
    if t not in SUPPORTED_TYPES:
        raise UnsupportedDevice(f"{t} is not covered by {METHOD_VERSION}")
    if not inputs.points:
        raise ValueError("device has no evidence")

    f = factors
    warnings = []
    factor_set = inputs.factor_set
    if t not in f["manufacturing"][factor_set]:
        warnings.append(f"{f['manufacturing'][factor_set]['label']} has no {t} value; using ADEME Base Carbone.")
        factor_set = "base_carbone"
    mf = f["manufacturing"][factor_set][t]
    M = (mf.get("A") or 0.0) + (mf.get("B") or 0.0)
    T = mf["transport"]
    band = f["manufacturing_band"][t]
    power = f["power_kw"][t]
    if "kwh_per_year" in power:  # phones and tablets: yearly energy over powered-on hours
        kwh_per_hour = power["kwh_per_year"] / power["powered_on_hours_per_year"]
    else:
        sleep = f["sleep_share"]["value"]
        kwh_per_hour = power["idle"] + power["sleep"] * sleep / (1 - sleep)
    typical = f["typical_first_life_hours"][t]
    life2_default = f["default_second_life"][t]
    rec = f["recycling_credit_kg"][t]
    min_h1 = f["min_valid_life1_hours"]["value"]
    window = f["first_life_grid_window_years"]["value"]

    country, warning = grid.resolve(inputs.country)
    if warning:
        warnings.append(warning)
    points = inputs.points
    reused = inputs.reuse_start is not None
    recycled = inputs.end_of_life and not reused
    start = inputs.reuse_start if reused else len(points) - 1

    # life 1: hours on the counter when the first life ended (or so far, if pending)
    raw_h1 = points[start].poh
    life1_measured = raw_h1 is not None and raw_h1 >= min_h1
    h1 = raw_h1 if life1_measured else typical

    # life 2: measured spans after the reuse start, else the thesis default
    h2, h2_measured, swaps = (0, False, 0)
    if reused:
        h2, h2_measured, swaps = _span_hours(points, start)
        if not h2_measured:
            h2 = life2_default["hours"]

    intake = points[start].date or points[0].date
    intake_year = intake.year if intake else (grid.latest_year(country) or 2025)
    F1 = grid.mean(country, intake_year - window, intake_year - 1)
    F2 = grid.mean(country, intake_year, intake_year + life2_default["years"] - 1)
    now_year = grid.latest_year(country) or intake_year
    F_now = grid.at(country, now_year)

    use1 = h1 * kwh_per_hour * F1
    use2 = h2 * kwh_per_hour * F2 if reused else 0.0
    legs = (
        f["weight_kg"][t] / 1000 * f["refurbisher_legs_km"]["value"] * f["van_kgco2e_per_tkm"]["value"]
        if reused else 0.0
    )

    impact = DeviceImpact(
        method_version=METHOD_VERSION,
        device_type=t,
        status="reused" if reused else ("recycled" if recycled else "pending"),
        reuse_source=inputs.reuse_source if reused else None,
        factor_set=factor_set,
        country=country,
        life1_hours=int(h1),
        life1_measured=life1_measured,
        hours_estimated=inputs.hours_method == HOURS_ANDROID_ESTIMATE,
        life2_hours=int(h2),
        life2_measured=h2_measured,
        life2_disk_swaps=swaps,
        grid_life1=F1,
        grid_life2=F2,
        grid_now=F_now,
        new_equivalent_kg=M + T,
    )
    impact.warnings.extend(warnings)

    impact.stages = {
        "manufacture": M,
        "transport": T + legs,
        "use1": use1,
        "refurbish": 0.0,  # not modelled in v0 (thesis p.115)
        "use2": use2,
        "end_of_life": rec if inputs.end_of_life else 0.0,
    }
    impact.second_life_ended = reused and inputs.end_of_life
    if recycled:
        impact.technician_hours = f["technician_hours"]["recycle"].get(t)

    if life1_measured:
        impact.unused_share = max(0.0, 1 - h1 / typical)
        impact.unused_kg = impact.unused_share * M

    impact.g_per_hour_life1 = 1000 * (M + T + use1) / h1

    if reused:
        life1_total, new_device = M + T + use1, M + T
        impact.s1 = life1_total + rec + new_device + use2
        impact.s2 = life1_total + legs + use2 + new_device + use2
        impact.s3 = life1_total + rec + 2 * new_device + 2 * use2
        impact.avoided = impact.s3 - impact.s2
        impact.cost_second_user = impact.s2 - impact.s1
        impact.avoided_low = band["p10"] + band["transport"] + rec - legs
        impact.avoided_high = band["p90"] + band["transport"] + rec - legs
        # current owner: unused manufacturing + delivery; no usable reading -> counted as new
        if life1_measured:
            expected_h2 = life2_default["hours"]  # fixed at handover, not re-counted at each scan
            impact.apos_share = expected_h2 / (h1 + expected_h2)
            impact.passed_on_kg = impact.apos_share * (M + T)
            impact.attributed_kg = impact.passed_on_kg + legs
        else:  # no usable reading: counted as new (conservative)
            impact.attributed_kg = M + T
        impact.g_per_hour_total = 1000 * (life1_total + legs + use2) / (h1 + h2)
        impact.technician_hours = f["technician_hours"]["reuse"].get(t)

        hpy, hpy_measured = life2_default["hours"] / life2_default["years"], False
        last = points[-1].date
        if h2_measured and intake and last:
            years = (last - intake).days / 365.25
            if years > 0.25:
                hpy, hpy_measured = h2 / years, True
        impact.hours_per_year = hpy
        impact.hours_per_year_measured = hpy_measured
        impact.kwh_per_year = hpy * kwh_per_hour
        impact.kg_per_year = impact.kwh_per_year * F_now

    if inputs.bios_year and intake:
        if reused:
            end = _year_fraction(intake) + life2_default["years"]
            if points[-1].date:
                end = max(end, _year_fraction(points[-1].date))
        else:
            end = _year_fraction(points[-1].date or intake)
        impact.lifetime_years = max(1.0, end - (inputs.bios_year + 0.5))

    impact.provenance = _provenance(inputs, impact, f, mf, factor_set)
    return impact


def _provenance(inputs, impact, f, mf, factor_set) -> list[Provenance]:
    hours_source = (
        "Android wear signals (DeviceHub estimator)" if impact.hours_estimated
        else "evidence power-on hours"
    )
    rows = [
        Provenance("life1_hours", f"{impact.life1_hours} h", impact.life1_measured,
                   hours_source if impact.life1_measured
                   else f"typical first life ({f['typical_first_life_hours'].get('mobile_ref') if inputs.device_type in ('smartphone', 'tablet') else f['typical_first_life_hours']['ref']})"),
        Provenance("manufacturing", f"{impact.new_equivalent_kg:.1f} kg", False,
                   f"{f['manufacturing'][factor_set]['label']}: {mf['ref']}"),
        Provenance("grid", f"{impact.grid_life1:.3f} → {impact.grid_life2:.3f} kg/kWh ({impact.country})",
                   False, "Our World in Data, thesis §6.6.1 windows"),
        Provenance("bios_year", str(inputs.bios_year) if inputs.bios_year else "unknown",
                   bool(inputs.bios_year), "evidence motherboard BIOS date"),
    ]
    if impact.reused:
        rows.insert(1, Provenance(
            "life2_hours", f"{impact.life2_hours} h", impact.life2_measured,
            f"{hours_source} after reuse start" if impact.life2_measured
            else f"thesis default second life ({f['default_second_life']['ref']})"))
        rows.append(Provenance("reuse_start", inputs.reuse_source or "", True, {
            "mark": "manual mark on an evidence",
            "transfer_state": "state that transfers the device (e.g. DONATION)",
            "outgoing_lot": "outgoing (Salida) lot",
        }.get(inputs.reuse_source, "second evidence")))
    return rows


# ---------------------------------------------------------------------------- lot


@dataclass
class LotImpact:
    method_version: str
    devices: int = 0
    reused: int = 0
    pending: int = 0
    recycled: int = 0
    second_lives_ended: int = 0
    unsupported: int = 0
    s1: float = 0.0
    s2: float = 0.0
    s3: float = 0.0
    avoided: float = 0.0
    avoided_low: float = 0.0
    avoided_high: float = 0.0
    cost_second_users: float = 0.0
    stages: dict = field(default_factory=dict)
    life2_hours_measured: int = 0
    life2_hours_projected: int = 0
    technician_hours: float = 0.0
    technician_hours_unknown: int = 0  # reused devices of a type with no labour source
    unused_kg: float = 0.0
    unused_kg_carried: float = 0.0
    passed_on_kg: float = 0.0  # APOS share taken on by second users
    unused_kg_lost: float = 0.0  # recycled before a second life
    devices_with_life1_reading: int = 0
    devices_past_typical_life: int = 0
    attributed_kg: float = 0.0
    new_equivalent_kg: float = 0.0
    counted_as_new: int = 0
    kwh_per_year: float = 0.0
    kg_per_year: float = 0.0

    @property
    def cost_with_new(self) -> float:
        return self.s3 - self.s1


def aggregate_lot(impacts: list[DeviceImpact], unsupported: int = 0) -> LotImpact:
    lot = LotImpact(method_version=METHOD_VERSION, unsupported=unsupported)
    for d in impacts:
        lot.devices += 1
        for k, v in d.stages.items():
            lot.stages[k] = lot.stages.get(k, 0.0) + v
        if d.unused_kg is not None:
            lot.devices_with_life1_reading += 1
            lot.unused_kg += d.unused_kg
            if d.unused_share == 0:
                lot.devices_past_typical_life += 1
        if d.recycled:
            lot.recycled += 1
            if d.unused_kg is not None:
                lot.unused_kg_lost += d.unused_kg
            if d.technician_hours is None:
                lot.technician_hours_unknown += 1
            else:
                lot.technician_hours += d.technician_hours
            continue
        if not d.reused:
            lot.pending += 1
            continue
        if d.second_life_ended:
            lot.second_lives_ended += 1
        lot.reused += 1
        lot.s1 += d.s1
        lot.s2 += d.s2
        lot.s3 += d.s3
        lot.avoided += d.avoided
        lot.avoided_low += d.avoided_low
        lot.avoided_high += d.avoided_high
        lot.cost_second_users += d.cost_second_user
        if d.life2_measured:
            lot.life2_hours_measured += d.life2_hours
        else:
            lot.life2_hours_projected += d.life2_hours
        if d.technician_hours is None:
            lot.technician_hours_unknown += 1
        else:
            lot.technician_hours += d.technician_hours
        if d.unused_kg is not None:
            lot.unused_kg_carried += d.unused_kg
        if d.passed_on_kg is not None:
            lot.passed_on_kg += d.passed_on_kg
        else:
            lot.counted_as_new += 1
        lot.attributed_kg += d.attributed_kg
        lot.new_equivalent_kg += d.new_equivalent_kg
        lot.kwh_per_year += d.kwh_per_year
        lot.kg_per_year += d.kg_per_year
    return lot
