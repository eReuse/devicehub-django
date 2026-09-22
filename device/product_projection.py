from dataclasses import dataclass, field

from device.models import Device
from evidence.models import Evidence


@dataclass
class ProjectionResult:
    product_type: str
    details: dict
    components: list = field(default_factory=list)
    attributes: dict = field(default_factory=dict)


class BaseProjection:
    """Newest-wins product view shared by every product type."""

    def __init__(self, product_type, evidences):
        self.product_type = product_type
        self.evidences = evidences

    def build(self):
        details = {
            "type": self.product_type,
            "manufacturer": "",
            "model": "",
            "version": "",
            "serial": "",
        }
        components = None
        attributes = None

        for evidence in self.evidences:
            try:
                values = self.detail_values(evidence)
                parsed = evidence.get_components()
            except Exception:
                continue

            for key, value in values.items():
                if not details[key] and value not in (None, ""):
                    details[key] = value

            if isinstance(parsed, list) and parsed and components is None:
                # A component list is one inventory at one point in time. Do
                # not union older lists: removed hardware would reappear.
                components = parsed
            elif evidence.is_web_snapshot() and isinstance(parsed, dict):
                if attributes is None:
                    attributes = parsed

        return ProjectionResult(
            product_type=self.product_type,
            details=details,
            components=components or [],
            attributes=attributes or {},
        )

    @staticmethod
    def detail_values(evidence):
        return {
            "type": evidence.get_chassis(),
            "manufacturer": evidence.get_manufacturer(),
            "model": evidence.get_model(),
            "version": evidence.get_version(),
            "serial": evidence.get_serial_number(),
        }


class ComputerProjection(BaseProjection):
    """Projection for computers using the standard component inventory."""


class MobileProjection(BaseProjection):
    """Projection for phones/tablets; diagnostics are added separately."""


class DefaultProjection(BaseProjection):
    """Projection for product types without specialized presentation."""


class ProjectionFactory:
    PROJECTIONS = {
        Device.Types.SMARTPHONE: MobileProjection,
        Device.Types.TABLET: MobileProjection,
        Device.Types.DESKTOP: ComputerProjection,
        Device.Types.LAPTOP: ComputerProjection,
        Device.Types.SERVER: ComputerProjection,
    }

    @classmethod
    def for_device(cls, device):
        evidences = cls.evidences_for(device)
        if not evidences:
            return None

        product_type = cls.detect_type(evidences)
        projection_class = cls.PROJECTIONS.get(product_type, DefaultProjection)
        return projection_class(product_type, evidences).build()

    @staticmethod
    def evidences_for(device):
        device.get_uuids()
        evidences = []
        for uuid in device.uuids:  # SystemProperty.created descending
            try:
                evidence = Evidence(uuid)
                if not evidence.is_photo_evidence():
                    evidences.append(evidence)
            except Exception:
                continue
        return evidences

    @classmethod
    def detect_type(cls, evidences):
        fallback = ""
        for evidence in evidences:
            try:
                product_type = evidence.get_chassis()
            except Exception:
                continue
            if product_type in cls.PROJECTIONS:
                return product_type
            if product_type and not fallback:
                fallback = product_type
        return fallback
