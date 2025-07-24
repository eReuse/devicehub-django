import os
import pickle
from device.models import Device
from ..algorithm_interface import EnvironmentImpactAlgorithm
from ..docs_renderer import render_docs
from environmental_impact.models import EnvironmentalImpact
from environmental_impact.algorithms import common
from .carbon_intensity import carbon_intensity


class SampleEnvironmentalImpactAlgorithm(EnvironmentImpactAlgorithm):

    algorithm_constants = {
        "AVG_KWATTS_TOWER": 0.039,
        "AVG_KWATTS_LAPTOP": 0.016,
    }

    def get_device_environmental_impact(self, device: Device) -> EnvironmentalImpact:
        env_impact = EnvironmentalImpact()
        env_impact.constants = self.algorithm_constants
        co2_emissions_in_use = self._compute_co2_emissions_while_in_use(device)
        env_impact.co2_emissions.update(co2_emissions_in_use)
        env_impact.docs = common.render_algorithm_docs(
            "docs.md", os.path.dirname(__file__)
        )
        env_impact.relevant_input_data = {
            "power_on_hours": common.get_power_on_hours_from(device),
            "carbon_intensity_factor": self._get_carbon_intensity_factor(device),
        }
        return env_impact

    def _compute_co2_emissions_while_in_use(self, device: Device) -> dict:
        power_on_hours = common.get_power_on_hours_from(device)
        energy_kwh = self._compute_energy_consumption_in_kwh(
            power_on_hours, device.type
        )
        co2_per_kwh = carbon_intensity.get_carbon_intensity_factor(
            "ESP"
        )  # TODO Default to Spain for now
        co2_consumption_in_use = energy_kwh * co2_per_kwh
        return {"in_use": co2_consumption_in_use, "co2_per_kwh_used": co2_per_kwh}

    def _compute_energy_consumption_in_kwh(
        self, power_on_hours: int, device_type: str
    ) -> float:
        if device_type == "Desktop":
            kwatts = 0.039  # AVG_KWATTS_TOWER
        elif device_type == "Laptop":
            kwatts = 0.016  # AVG_KWATTS_LAPTOP
        else:
            raise ValueError(f"Unknown device type: {device_type}")
        return power_on_hours * kwatts
