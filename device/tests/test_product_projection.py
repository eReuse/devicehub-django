from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from device.product_projection import ProjectionFactory


def evidence(evidence_uuid, timestamp=None):
    return SimpleNamespace(
        uuid=evidence_uuid,
        doc={"timestamp": timestamp} if timestamp else {},
        get_time_created=lambda: None,
        is_photo_evidence=lambda: False,
    )


class ProjectionEvidenceOrderingTests(SimpleTestCase):
    @patch("device.product_projection.Evidence")
    def test_orders_by_snapshot_date_instead_of_upload_order(self, evidence_class):
        by_uuid = {
            "uploaded-last": evidence("uploaded-last", "2025-12-01 09:00:00"),
            "uploaded-first": evidence("uploaded-first", "2026-01-01T09:00:00Z"),
            "without-date": evidence("without-date"),
        }
        evidence_class.side_effect = by_uuid.__getitem__
        device = SimpleNamespace(
            # Device.get_uuids() normally supplies upload-date descending.
            uuids=["uploaded-last", "without-date", "uploaded-first"],
            get_uuids=Mock(),
        )

        projected = ProjectionFactory.evidences_for(device)

        self.assertEqual(
            [item.uuid for item in projected],
            ["uploaded-first", "uploaded-last", "without-date"],
        )
