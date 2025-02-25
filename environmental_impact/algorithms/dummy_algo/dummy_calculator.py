from device.models import Device
from ..algorithm_interface import EnvironmentImpactAlgorithm
from environmental_impact.models import EnvironmentalImpact


class DummyEnvironmentalImpactAlgorithm(EnvironmentImpactAlgorithm):

    def get_device_environmental_impact(self, device: Device) -> EnvironmentalImpact:
        # TODO Make a constants file / class
        avg_watts = 40  # Arbitrary laptop average consumption
        co2_per_kwh = 0.475
        power_on_hours = self.get_power_on_hours_from(device)
        energy_kwh = (power_on_hours * avg_watts) / 1000
        co2_emissions = energy_kwh * co2_per_kwh
        return EnvironmentalImpact(co2_emissions=co2_emissions)

    def get_power_on_hours_from(self, device: Device) -> int:
        # TODO how do I check if the device is a legacy workbench? Is there a better way?
        is_legacy_workbench = False if device.last_evidence.inxi else True
        if not is_legacy_workbench:
            storage_components = device.components[9]
            str_time = storage_components.get('time of used', -1)
        else:
            str_time = ""
        uptime_in_hours = self.convert_str_time_to_hours(str_time, is_legacy_workbench)
        return uptime_in_hours

    def convert_str_time_to_hours(self, time_str: str, is_legacy_workbench: bool) -> int:
        if is_legacy_workbench:
            return -1  # TODO  Power on hours not available in legacy workbench
        else:
            multipliers = {'y': 365 * 24, 'd': 24, 'h': 1}
            return sum(int(part[:-1]) * multipliers[part[-1]] for part in time_str.split())
