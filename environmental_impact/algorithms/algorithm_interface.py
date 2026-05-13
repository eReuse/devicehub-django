from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from device.models import Device
from environmental_impact.models import EnvironmentalImpact

if TYPE_CHECKING:
    from user.models import Institution


class EnvironmentImpactAlgorithm(ABC):

    @abstractmethod
    def get_device_environmental_impact(
        self, device: Device, institution: Institution | None = None
    ) -> EnvironmentalImpact:
        pass

    @abstractmethod
    def get_lot_environmental_impact(
        self, devices: list[Device], institution: Institution | None = None
    ) -> EnvironmentalImpact:
        pass
