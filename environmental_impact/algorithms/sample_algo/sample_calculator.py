import os
from device.models import Device
from ..algorithm_interface import EnvironmentImpactAlgorithm
from environmental_impact.models import EnvironmentalImpact
from ..common import (
    get_poh_from_device,
    render_algorithm_docs,
    compute_energy_consumption_kwh,
    compute_co2_emissions,
)


class SampleEnvironmentalImpactAlgorithm(EnvironmentImpactAlgorithm):

    algorithm_constants = {
        "AVG_WATTS": 100,
        "CO2_PER_KWH": 0.233,
    }

    def get_device_environmental_impact(self, device: Device) -> EnvironmentalImpact:
        env_impact = EnvironmentalImpact()
        env_impact.constants = self.algorithm_constants
        co2_emissions_in_use = self.compute_co2_emissions_while_in_use(device)
        env_impact.kg_CO2e.update(co2_emissions_in_use)
        env_impact.docs = render_algorithm_docs("docs.md", os.path.dirname(__file__))
        env_impact.relevant_input_data = {
            "power_on_hours": get_poh_from_device(device)
        }
        return env_impact

    def compute_co2_emissions_while_in_use(self, device: Device) -> dict:
        power_on_hours = get_poh_from_device(device)
        energy_kwh = compute_energy_consumption_kwh(
            power_on_hours, self.algorithm_constants["AVG_WATTS"]
        )
        co2_consumption_in_use = compute_co2_emissions(
            energy_kwh, self.algorithm_constants["CO2_PER_KWH"]
        )
        return {"in_use": co2_consumption_in_use}
