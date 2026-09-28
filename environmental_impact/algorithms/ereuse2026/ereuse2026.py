from __future__ import annotations

import json
import logging
import os
import re
from functools import lru_cache
from typing import TYPE_CHECKING

from device.models import Device
from environmental_impact.algorithms import common
from environmental_impact.algorithms.algorithm_interface import EnvironmentImpactAlgorithm
from environmental_impact.algorithms.ereuse2025.carbon_intensity import get_carbon_intensity_data
from environmental_impact.algorithms.ereuse2025.disk_change_detector import detect_disk_changes
from environmental_impact.algorithms.ereuse2025.lifecycle_extractors import get_evidences_data_from_device
from environmental_impact.models import EnvironmentalImpact
from environmental_impact.reuse import read_reuse_signals, resolve_reuse
from utils.constants import CHASSIS_DH

from .model import (
    HOURS_ANDROID_ESTIMATE,
    HOURS_COUNTER,
    DeviceInputs,
    EvidencePoint,
    GridSeries,
    UnsupportedDevice,
    aggregate_lot,
    compute_device,
)

if TYPE_CHECKING:
    from user.models import Institution

logger = logging.getLogger(__name__)

HERE = os.path.dirname(__file__)
DEFAULT_COUNTRY_CODE = "ES"
MOBILE_TYPES = ("smartphone", "tablet")
# DeviceHub stores either a device type ("Desktop") or a raw chassis name
# ("Mini-tower", "Netbook"). Group them with utils.constants.CHASSIS_DH.
CHASSIS_GROUPS = {
    "Desktop": "desktop", "Microtower": "desktop", "AllInOne": "desktop",
    "PizzaBox": "desktop", "Lunchbox": "desktop", "Stick": "desktop",
    "Laptop": "laptop", "Convertible": "laptop",
    "Tablet": "tablet", "Detachable": "tablet",
}
NOT_COVERED = {"server"}  # different power profile; not in the factor set


def model_device_type(device_type: str | None) -> str | None:
    """"desktop" | "laptop" | "smartphone" | "tablet", or None if not covered."""
    name = (device_type or "").strip().lower()
    if not name or name in NOT_COVERED:
        return None
    if name == Device.Types.SMARTPHONE.lower():
        return "smartphone"
    for group, model_type in CHASSIS_GROUPS.items():
        if name == group.lower() or name in CHASSIS_DH.get(group, set()):
            return model_type
    return None
YEAR_RE = re.compile(r"\b(19[89]\d|20\d\d)\b")


@lru_cache(maxsize=1)
def load_factors() -> dict:
    with open(os.path.join(HERE, "factors.json"), encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_grid() -> GridSeries:
    with open(os.path.join(HERE, "grid_intensity_series.json"), encoding="utf-8") as f:
        series = json.load(f)
    return GridSeries(series, latest=get_carbon_intensity_data(), default_country=DEFAULT_COUNTRY_CODE)


def render_docs() -> str:
    return common.render_algorithm_docs("docs.md", HERE)


def bios_year_from_components(components: list | None) -> int | None:
    for comp in components or []:
        if comp.get("type") == "Motherboard" and comp.get("biosDate"):
            match = YEAR_RE.search(str(comp["biosDate"]))
            if match:
                return int(match.group(1))
    return None


def build_inputs(device: Device, institution: "Institution" | None, factor_set: str = "base_carbone") -> DeviceInputs:
    device_type = model_device_type(device.type)
    if not device_type:
        raise UnsupportedDevice(f"{device.type} is not covered by ereuse2026")

    evidences = get_evidences_data_from_device(device)
    changed = set(detect_disk_changes(evidences)) if len(evidences) > 1 else set()
    points = [
        EvidencePoint(uuid=str(e.uuid), date=e.date, poh=e.poh, disk_changed=i in changed)
        for i, e in enumerate(evidences)
    ]

    signals = read_reuse_signals(device, institution or getattr(device, "owner", None))
    reuse_start, reuse_source = resolve_reuse([(p.uuid, p.date) for p in points], signals)

    bios_year = None
    last = getattr(device, "last_evidence", None)
    if last is not None:
        try:
            bios_year = bios_year_from_components(last.get_components())
        except Exception:  # a malformed snapshot should not break the impact tab
            logger.debug("no BIOS date for %s", device.id, exc_info=True)

    return DeviceInputs(
        device_type=device_type,
        points=points,
        country=common.get_device_country_code(device, institution, DEFAULT_COUNTRY_CODE),
        reuse_start=reuse_start,
        reuse_source=reuse_source,
        bios_year=bios_year,
        factor_set=factor_set,
        hours_method=HOURS_ANDROID_ESTIMATE if device_type in MOBILE_TYPES else HOURS_COUNTER,
        end_of_life=signals.end_of_life,
    )


class EReuse2026EnvironmentalImpactAlgorithm(EnvironmentImpactAlgorithm):
    """Scenario model (Roura Salietti 2025) with ITU-T L.1410 stages. See docs.md."""

    def __init__(self, factor_set: str = "base_carbone"):
        self.factor_set = factor_set

    def compute(self, device: Device, institution: "Institution" | None = None):
        """The ``DeviceImpact`` for one device; raises ``UnsupportedDevice``."""
        return self.compute_with_inputs(device, institution)[1]

    def compute_with_inputs(self, device: Device, institution: "Institution" | None = None):
        """``(DeviceInputs, DeviceImpact)``: the device tab also needs the timeline."""
        inputs = build_inputs(device, institution, self.factor_set)
        return inputs, compute_device(inputs, load_factors(), load_grid())

    def get_device_environmental_impact(
        self, device: Device, institution: "Institution" | None = None
    ) -> EnvironmentalImpact:
        impact = self.compute(device, institution)
        return self._wrap(impact)

    def get_lot_environmental_impact(
        self, devices: list[Device], institution: "Institution" | None = None
    ) -> EnvironmentalImpact:
        impacts, unsupported = [], 0
        for device in devices:
            try:
                impacts.append(self.compute(device, institution))
            except UnsupportedDevice:
                unsupported += 1
            except ValueError:  # no evidence
                unsupported += 1
        env = EnvironmentalImpact()
        env.lot = aggregate_lot(impacts, unsupported=unsupported)
        env.device_impacts = impacts
        env.kg_CO2e = {"in_use": sum(i.use_phase_kg for i in impacts)}
        env.relevant_input_data = {
            "total_devices": len(devices),
            "reused_devices": env.lot.reused,
            "method_version": env.lot.method_version,
        }
        env.docs = render_docs()
        return env

    def _wrap(self, impact) -> EnvironmentalImpact:
        env = EnvironmentalImpact()
        env.model = impact
        # Kept for templates and callers written for ereuse2025.
        env.kg_CO2e = {"in_use": impact.use_phase_kg}
        env.relevant_input_data = {
            "total_usage_time": impact.life1_hours + impact.life2_hours,
            "reuse_time": impact.life2_hours if impact.reused else 0,
            "country_code": impact.country,
            "carbon_intensity_factor": round(impact.grid_now * 1000, 3),
            "device_type": impact.device_type,
            "method_version": impact.method_version,
        }
        if impact.warnings:
            env.relevant_input_data["warnings"] = list(impact.warnings)
        env.constants = {"factor_set": impact.factor_set}
        env.docs = render_docs()
        return env
