from types import SimpleNamespace

from django.test import TestCase

from environmental_impact.algorithms.ereuse2025.lifecycle_extractors import (
    get_evidences_data_from_device,
)


class LifecycleExtractorsTests(TestCase):
    def test_get_evidences_data_sorts_by_evidence_timestamp(self):
        older = SimpleNamespace(
            uuid="older",
            doc={"timestamp": "2026-03-23 10:32:16.413555"},
            inxi=True,
            get_time_created=lambda: "2026-05-20T14:43:36.535743",
            get_components=lambda: [
                {
                    "type": "Storage",
                    "time of used": "45d 6h",
                    "serialNumber": "disk-1",
                    "model": "disk-model",
                    "manufacturer": "disk-maker",
                }
            ],
        )
        newer = SimpleNamespace(
            uuid="newer",
            doc={"timestamp": "2026-04-10 11:42:52.527352"},
            inxi=True,
            get_time_created=lambda: "2026-05-20T14:43:36.333376",
            get_components=lambda: [
                {
                    "type": "Storage",
                    "time of used": "46d 5h",
                    "serialNumber": "disk-1",
                    "model": "disk-model",
                    "manufacturer": "disk-maker",
                }
            ],
        )
        device = SimpleNamespace(evidences=[newer, older])

        evidences_data = get_evidences_data_from_device(device)

        self.assertEqual([e.uuid for e in evidences_data], ["older", "newer"])
        self.assertEqual([e.poh for e in evidences_data], [1086, 1109])
