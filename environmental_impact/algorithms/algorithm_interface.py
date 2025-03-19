from abc import ABC, abstractmethod
from functools import lru_cache
from device.models import Device
from environmental_impact.models import EnvironmentalImpact


class EnvironmentImpactAlgorithm(ABC):

    @abstractmethod
    def get_device_environmental_impact(self, device: Device) -> EnvironmentalImpact:
        pass