from dataclasses import dataclass
from device.models import Device


@dataclass
class EnvironmentalImpact:
    carbon_saved: float = 0.0
    co2_emissions: float = 0.0


def get_device_environmental_impact(device: Device) -> EnvironmentalImpact:
    avg_watts = 40  # Arbitrary laptop average consumption
    power_on_hours = get_power_on_hours_from(device)
    energy_kwh = (power_on_hours * avg_watts) / 1000
    # CO2 emissions based on global average electricity mix
    co2_per_kwh = 0.475
    co2_emissions = energy_kwh * co2_per_kwh
    return EnvironmentalImpact(co2_emissions=co2_emissions)


def get_power_on_hours_from(device: Device) -> int:
    storage_components = device.components[9]
    str_time = storage_components.get('time of used', -1)
    uptime_in_hours = convert_str_time_to_hours(str_time)
    return uptime_in_hours


def convert_str_time_to_hours(time_str: str) -> int:
    multipliers = {'y': 365 * 24, 'd': 24, 'h': 1}
    return sum(int(part[:-1]) * multipliers[part[-1]] for part in time_str.split())
