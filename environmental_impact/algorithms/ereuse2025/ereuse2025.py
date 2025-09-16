import os
from device.models import Device
from ..algorithm_interface import EnvironmentImpactAlgorithm
from environmental_impact.models import EnvironmentalImpact
from environmental_impact.algorithms import common
from .carbon_intensity import carbon_intensity

class EReuse2025EnvironmentalImpactAlgorithm(EnvironmentImpactAlgorithm):
    algorithm_constants = {
        "AVG_KWATTS_DESKTOP_IDLE": 0.039,
        "AVG_KWATTS_LAPTOP_IDLE": 0.016,
        "AVG_KWATTS_DEFAULT_IDLE": 0.02,  # TODO Default average power consumption??
        "MEAN_PERCENTAGE_DEVICE_IS_SLEEPING": 0.2562,  # From energy star DB
        "AVG_KWATTS_DESKTOP_SLEEP": 0.0016,
        "AVG_KWATTS_LAPTOP_SLEEP": 0.0005,
        "AVG_KWATTS_DEFAULT_SLEEP": 0.001,  # TODO Default sleep power consumption?
    }

    def get_device_environmental_impact(self, device: Device) -> EnvironmentalImpact:
        env_impact = EnvironmentalImpact()
        env_impact.constants = self.algorithm_constants
        kg_CO2e = self._compute_co2_emissions_while_in_use(device)
        env_impact.kg_CO2e.update(kg_CO2e)
        env_impact.docs = common.render_algorithm_docs(
            "docs.md", os.path.dirname(__file__)
        )
        env_impact.relevant_input_data = {
            "power_on_hours": common.get_power_on_hours_from(device),
            "hours_in_sleep_mode": self._get_time_while_in_sleep_mode(
                common.get_power_on_hours_from(device)
            ),
            "carbon_intensity_factor": carbon_intensity.get_carbon_intensity_factor_from(
                "ES"  # TODO Default to Spain for now
            ),
            "device_type": device.type,
        }
        return env_impact

    def _compute_co2_emissions_while_in_use(self, device: Device) -> dict:
        power_on_hours = common.get_power_on_hours_from(device)
        energy_kwh_idle = self._compute_energy_consumption_in_kwh_while_idle(
            power_on_hours, device.type
        )
        energy_kwh_sleeping = self._compute_energy_consumption_while_sleeping(
            power_on_hours, device.type
        )
        carbon_intensity_factor = carbon_intensity.get_carbon_intensity_factor_from(
            "ES"
        )  # TODO Default to Spain for now
        kgco2e_consumption_in_use = (
            carbon_intensity_factor * (energy_kwh_idle + energy_kwh_sleeping) / 1000
        )
        return {
            "in_use": kgco2e_consumption_in_use,
            "carbon_intensity_factor": carbon_intensity_factor,
        }

    def _compute_energy_consumption_in_kwh_while_idle(
        self, power_on_hours: int, device_type: str
    ) -> float:
        if device_type == Device.Types.DESKTOP:
            kwatts = self.algorithm_constants["AVG_KWATTS_DESKTOP_IDLE"]
        elif device_type == Device.Types.LAPTOP:
            kwatts = self.algorithm_constants["AVG_KWATTS_LAPTOP_IDLE"]
        elif device_type in Device.Types.values:
            kwatts = self.algorithm_constants["AVG_KWATTS_DEFAULT_IDLE"]
        else:
            kwatts = self.algorithm_constants["AVG_KWATTS_DEFAULT_IDLE"]
        return power_on_hours * kwatts

    def _get_time_while_in_sleep_mode(self, power_on_hours: int) -> int:
        time_in_sleep_mode = (
            self.algorithm_constants["MEAN_PERCENTAGE_DEVICE_IS_SLEEPING"]
            * power_on_hours
        ) / (1 - self.algorithm_constants["MEAN_PERCENTAGE_DEVICE_IS_SLEEPING"])
        return int(time_in_sleep_mode)

    def _compute_energy_consumption_while_sleeping(
        self, power_on_hours: int, device_type: str
    ) -> float:
        time_in_sleep_mode = self._get_time_while_in_sleep_mode(power_on_hours)
        if device_type == Device.Types.DESKTOP:
            kwatts = self.algorithm_constants["AVG_KWATTS_DESKTOP_SLEEP"]
        elif device_type == Device.Types.LAPTOP:
            kwatts = self.algorithm_constants["AVG_KWATTS_LAPTOP_SLEEP"]
        elif device_type in Device.Types.values:
            kwatts = self.algorithm_constants["AVG_KWATTS_DEFAULT_SLEEP"]
        else:
            kwatts = self.algorithm_constants["AVG_KWATTS_DEFAULT_SLEEP"]
        return time_in_sleep_mode * kwatts
