from dataclasses import dataclass, field

from device.models import Device
from environmental_impact.algorithms.ereuse2025.lifecycle_extractors import (
    get_evidence_datetime,
)
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
        projection = projection_class(product_type, evidences).build()
        return cls.with_device_fallback(projection, device)

    @staticmethod
    def with_device_fallback(projection, device):
        """Keep the established Device presentation when projection is sparse.

        Evidence aggregation is useful when a product has several snapshots,
        but it must not make older product types less informative.  Device's
        existing properties already describe the selected evidence, so use
        them only for fields the projection could not obtain.
        """
        fallback_attributes = {
            "type": "type",
            "manufacturer": "manufacturer",
            "model": "model",
            "version": "version",
            "serial": "serial_number",
        }
        for key, attribute in fallback_attributes.items():
            if projection.details.get(key) not in (None, ""):
                continue
            try:
                value = getattr(device, attribute)
            except Exception:
                continue
            if value not in (None, ""):
                projection.details[key] = value

        if not projection.components:
            try:
                projection.components = device.components or []
            except Exception:
                pass

        if not projection.attributes:
            try:
                if device.is_websnapshot:
                    projection.attributes = dict(device.last_user_evidence)
            except Exception:
                pass

        projection.product_type = projection.details.get("type", "")
        return projection

    @staticmethod
    def evidences_for(device):
        device.get_uuids()
        dated_evidences = []
        undated_evidences = []
        for uuid in device.uuids:
            try:
                evidence = Evidence(uuid)
                if evidence.is_photo_evidence():
                    continue
                evidence_datetime = get_evidence_datetime(evidence)
                if evidence_datetime:
                    dated_evidences.append((evidence_datetime, evidence))
                else:
                    undated_evidences.append(evidence)
            except Exception:
                continue

        dated_evidences.sort(
            key=lambda item: (item[0], str(item[1].uuid)),
            reverse=True,
        )
        undated_evidences.sort(key=lambda evidence: str(evidence.uuid))
        return [evidence for _, evidence in dated_evidences] + undated_evidences

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
