import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from django.test import TestCase

from environmental_impact.algorithms.ereuse2025.lifecycle_extractors import (
    get_evidence_datetime,
    get_evidences_data_from_device,
)
from environmental_impact.algorithms.ereuse2025.time_calculations import (
    calculate_reuse_time,
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

    def test_get_evidences_data_uses_real_namibia_ordering_fixture(self):
        fixture_path = (
            Path(__file__).resolve().parent
            / "fixtures"
            / "namibia_lifecycle_ordering.json"
        )
        fixture = json.loads(fixture_path.read_text())

        uploaded_newer_first = []
        for item in reversed(fixture):
            uploaded_newer_first.append(
                SimpleNamespace(
                    uuid=item["uuid"],
                    doc={"timestamp": item["timestamp"]},
                    inxi=True,
                    get_time_created=lambda uploaded_at=item["uploaded_at"]: uploaded_at,
                    get_components=lambda storage=item["storage"]: [storage],
                )
            )

        device = SimpleNamespace(evidences=uploaded_newer_first)

        evidences_data = get_evidences_data_from_device(device)

        self.assertEqual(
            [e.uuid for e in evidences_data],
            [
                "7ee57700-cb7f-418e-b7ce-8aab97ada02a",
                "3bcfe16c-7834-4ba3-9507-ddc31e8f4fea",
            ],
        )
        self.assertEqual([e.poh for e in evidences_data], [1086, 1109])
        self.assertEqual(calculate_reuse_time(evidences_data), 23)

    def test_get_evidences_data_sorts_mixed_timezone_formats(self):
        def evidence(uuid, doc, poh):
            return SimpleNamespace(
                uuid=uuid,
                doc=doc,
                inxi=True,
                get_time_created=lambda: "2026-05-20T14:43:36.535743+00:00",
                get_components=lambda: [
                    {
                        "type": "Storage",
                        "time of used": poh,
                        "serialNumber": "disk-1",
                        "model": "disk-model",
                        "manufacturer": "disk-maker",
                    }
                ],
            )

        # Legacy Workbench dates are aware, workbench-script dates are naive.
        legacy = evidence("legacy", {"endTime": "2022-06-09T12:10:50.809Z"}, "45d 6h")
        script = evidence("script", {"timestamp": "2025-12-06 09:00:00.000000"}, "46d 5h")
        device = SimpleNamespace(evidences=[script, legacy])

        evidences_data = get_evidences_data_from_device(device)

        self.assertEqual([e.uuid for e in evidences_data], ["legacy", "script"])

    def test_get_evidence_datetime_reads_naive_values_as_utc(self):
        evidence = SimpleNamespace(
            uuid="naive",
            doc={"timestamp": "2025-12-06 09:00:00"},
            get_time_created=lambda: None,
        )

        self.assertEqual(
            get_evidence_datetime(evidence),
            datetime(2025, 12, 6, 9, 0, tzinfo=timezone.utc),
        )
