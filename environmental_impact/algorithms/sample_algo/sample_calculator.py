import os
from device.models import Device
from ..algorithm_interface import EnvironmentImpactAlgorithm
from environmental_impact.models import EnvironmentalImpact
from ..docs_renderer import render_docs


class SampleEnvironmentalImpactAlgorithm(EnvironmentImpactAlgorithm):

    algorithm_constants = {
        "AVG_WATTS": 100,
        "CO2_PER_KWH": 0.233,
    }

    def get_device_environmental_impact(self, device: Device) -> EnvironmentalImpact:

        env_impact = EnvironmentalImpact()
        env_impact.constants = self.algorithm_constants
        co2_emissions_in_use = self.compute_co2_emissions_while_in_use(device)
        env_impact.co2_emissions.update(co2_emissions_in_use)
        env_impact.docs = self.render_docs_from("docs.md")
        env_impact.relevant_input_data = {
            "power_on_hours": self.get_power_on_hours_from(device)
        }
        return env_impact

    def compute_co2_emissions_while_in_use(self, device: Device) -> dict:
        power_on_hours = self.get_power_on_hours_from(device)
        energy_kwh = self.compute_energy_consumption_in_kwh(power_on_hours)
        co2_consumption_in_use = energy_kwh * self.algorithm_constants["CO2_PER_KWH"]
        return {"in_use": co2_consumption_in_use}

    def render_docs_from(self, docs_path: str = "docs.md") -> str:
        current_dir = os.path.dirname(__file__)
        docs_path = os.path.join(current_dir, "docs.md")
        docs = render_docs(docs_path)
        return docs

    def get_power_on_hours_from(self, device: Device) -> int:
        is_legacy_workbench = False if device.last_evidence.inxi else True
        if is_legacy_workbench:
            return -1
        else:
            storage_components = next(
                (comp for comp in device.components if comp["type"] == "Storage"), None
            )
            str_time = storage_components.get("time of used", "")
            uptime_in_hours = self.convert_str_time_to_hours(str_time)
        return uptime_in_hours

    def convert_str_time_to_hours(self, time_str: str) -> int:
        multipliers = {"y": 365 * 24, "d": 24, "h": 1}
        return sum(int(part[:-1]) * multipliers[part[-1]] for part in time_str.split())

    def compute_energy_consumption_in_kwh(self, power_on_hours: int) -> float:
        return power_on_hours * self.algorithm_constants["AVG_WATTS"] / 1000
