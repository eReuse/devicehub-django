from dataclasses import dataclass


@dataclass
class EnvironmentalImpact:
    carbon_saved: float


def get_device_environmental_impact() -> EnvironmentalImpact:
    return EnvironmentalImpact(carbon_saved=225.0)
