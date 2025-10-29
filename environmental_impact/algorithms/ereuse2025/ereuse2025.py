import os
from device.models import Device
from ..algorithm_interface import EnvironmentImpactAlgorithm
from environmental_impact.models import EnvironmentalImpact
from environmental_impact.algorithms import common
from .carbon_intensity import carbon_intensity
from .lifecycle_extractors import get_evidences_data_from_device
from .disk_change_detector import detect_disk_changes
from .time_calculations import calculate_total_usage_time, calculate_reuse_time


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
        lifecycle_metrics = self._calculate_lifecycle_metrics(device)
        total_usage_time = lifecycle_metrics["total_usage_time"]
        kg_CO2e = self._compute_co2_emissions_while_in_use_with_lifecycle(
            total_usage_time, device.type
        )
        env_impact.kg_CO2e.update(kg_CO2e)
        env_impact.docs = common.render_algorithm_docs(
            "docs.md", os.path.dirname(__file__)
        )
        env_impact.relevant_input_data = {
            "total_usage_time": total_usage_time,
            "reuse_time": lifecycle_metrics["reuse_time"],
            "evidence_count": lifecycle_metrics["evidence_count"],
            "disk_change_count": lifecycle_metrics["disk_change_count"],
            "hours_in_sleep_mode": self._get_time_while_in_sleep_mode(total_usage_time),
            "carbon_intensity_factor": (
                carbon_intensity.get_carbon_intensity_factor_from(
                    "ES"
                )  # TODO Default to Spain for now
            ),
            "device_type": device.type,
        }
        return env_impact

    def _calculate_lifecycle_metrics(self, device: Device) -> dict:
        """
        Calculate lifecycle metrics (T_T, T_R) from all device evidences.

        Returns dict with total_usage_time, reuse_time, evidence_count,
        and disk_change_count.
        """
        evidences_data = get_evidences_data_from_device(device)

        if not evidences_data:
            # Fallback to single evidence if no evidences found
            return {
                "total_usage_time": common.get_poh_from_device(device),
                "reuse_time": 0,
                "evidence_count": 1 if device.last_evidence else 0,
                "disk_change_count": 0,
            }

        disk_change_indices = detect_disk_changes(evidences_data)
        total_usage_time = calculate_total_usage_time(
            evidences_data, disk_change_indices
        )
        reuse_time = calculate_reuse_time(evidences_data)

        return {
            "total_usage_time": total_usage_time,
            "reuse_time": reuse_time,
            "evidence_count": len(evidences_data),
            "disk_change_count": len(disk_change_indices),
        }

    def _compute_co2_emissions_while_in_use_with_lifecycle(
        self, total_usage_time: int, device_type: str
    ) -> dict:
        """Compute CO2 emissions using lifecycle total usage time."""
        energy_kwh_idle = self._compute_energy_consumption_in_kwh_while_idle(
            total_usage_time, device_type
        )
        energy_kwh_sleeping = self._compute_energy_consumption_while_sleeping(
            total_usage_time, device_type
        )
        carbon_intensity_factor = carbon_intensity.get_carbon_intensity_factor_from(
            "ES"
        )
        kgco2e_consumption_in_use = (
            carbon_intensity_factor * (energy_kwh_idle + energy_kwh_sleeping) / 1000
        )
        return {
            "in_use": kgco2e_consumption_in_use,
            "carbon_intensity_factor": carbon_intensity_factor,
        }

    def _compute_co2_emissions_while_in_use(self, device: Device) -> dict:
        power_on_hours = common.get_poh_from_device(device)
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

    def get_lot_environmental_impact(
        self, devices: list[Device]
    ) -> EnvironmentalImpact:
        env_impact = EnvironmentalImpact()
        env_impact.constants = self.algorithm_constants
        total_kg_CO2e = {"in_use": 0.0, "carbon_intensity_factor": 0.0}
        for device in devices:
            device_env_impact = self.get_device_environmental_impact(device)
            total_kg_CO2e["in_use"] += device_env_impact.kg_CO2e.get("in_use", 0.0)
        env_impact.kg_CO2e = total_kg_CO2e
        env_impact.docs = (
            common.render_algorithm_docs("docs.md", os.path.dirname(__file__))
            + "\n\n## Lot Aggregation\n"
            "This impact calculation aggregates individual device impacts:\n"
            f"- Total devices in lot: {len(devices)}\n"
            f"- CO2e emissions are summed across all devices. Total: {env_impact.kg_CO2e} kgCO2e\n"
        )
        return env_impact
