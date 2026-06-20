import uuid

from django.test import TestCase

from user.models import Institution, User
from evidence.parse import Build
from evidence.models import SystemProperty, RootAlias


def mobile_snapshot(manual_id, app_uuid="app-uuid", ev_uuid=None):
    """A workbench-android snapshot, as produced by the Android app."""
    serial = manual_id or app_uuid
    return {
        "timestamp": "2026-06-18T20:00:00Z",
        "type": "Snapshot",
        "uuid": ev_uuid or str(uuid.uuid4()),
        "software": "workbench-android",
        "version": "0.1.0",
        "data": {
            "device": {
                "type": "Smartphone",
                "chassis": "Handheld",
                "manufacturer": "Google",
                "model": "Pixel 6",
                "serial_number": serial,
                "manual_id": manual_id,
            },
            "android": {
                "manufacturer": "Google",
                "brand": "google",
                "model": "Pixel 6",
                "android_version": "15",
                "api_level": 35,
                "build_fingerprint": "google/...",
            },
            "usage": {"usage_category": "UNKNOWN", "usage_confidence": "LOW"},
            "hwtest": {"verdict": "OK", "results": []},
        },
    }


class MobileSnapshotTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name="Test", country="ES")
        self.user = User.objects.create_user("u@example.org", self.institution, "1234")

    def test_builds_smartphone_chid(self):
        snap = mobile_snapshot("AUCOOP-0042")
        Build(snap, self.user)

        prop = SystemProperty.objects.filter(
            uuid=snap["uuid"], key="ereuse24", owner=self.institution
        ).first()
        self.assertIsNotNone(prop)
        self.assertTrue(prop.value.startswith("ereuse24:"))

    def test_manual_id_creates_custom_id_root_alias(self):
        snap = mobile_snapshot("AUCOOP-0042")
        Build(snap, self.user)

        prop = SystemProperty.objects.get(
            uuid=snap["uuid"], key="ereuse24", owner=self.institution
        )
        alias = RootAlias.objects.filter(owner=self.institution, alias=prop.value).first()
        self.assertIsNotNone(alias)
        self.assertEqual(alias.root, "custom_id:AUCOOP-0042")

    def test_same_manual_id_collapses_to_one_device(self):
        # Two scans, same sticker, different app UUID (e.g. after factory reset).
        Build(mobile_snapshot("AUCOOP-0042", app_uuid="uuid-A"), self.user)
        Build(mobile_snapshot("AUCOOP-0042", app_uuid="uuid-B"), self.user)

        chids = set(
            SystemProperty.objects.filter(
                key="ereuse24", owner=self.institution
            ).values_list("value", flat=True)
        )
        self.assertEqual(len(chids), 1)
        # alias creation is idempotent (owner, alias) unique
        self.assertEqual(RootAlias.objects.filter(owner=self.institution).count(), 1)

    def test_different_manual_id_two_devices(self):
        Build(mobile_snapshot("AUCOOP-0001"), self.user)
        Build(mobile_snapshot("AUCOOP-0002"), self.user)

        chids = set(
            SystemProperty.objects.filter(
                key="ereuse24", owner=self.institution
            ).values_list("value", flat=True)
        )
        self.assertEqual(len(chids), 2)

    def test_components_from_android_block(self):
        from evidence.parse_details import ParseSnapshot

        snap = mobile_snapshot("AUCOOP-COMP")
        snap["data"]["android"].update({
            "cpu": {"soc_model": "Tensor", "cores": 8, "abis": ["arm64-v8a"]},
            "memory": {"total_bytes": 8 * 1024 ** 3},
            "storage": {"total_bytes": 128 * 1024 ** 3, "free_bytes": 100 * 1024 ** 3},
            "display": {"width_px": 1080, "height_px": 2400, "density_dpi": 420},
            "battery": {"level_percent": 85, "technology": "Li-ion"},
            "cameras": [{"id": "0", "lens_facing": "back", "megapixels": 50.0}],
        })

        comps = ParseSnapshot(snap).components
        types = {c["type"] for c in comps}
        self.assertTrue(
            {"Processor", "RamModule", "Storage", "Display", "Battery", "Camera"} <= types,
            types,
        )

    def test_no_manual_id_no_alias(self):
        Build(mobile_snapshot(None, app_uuid="uuid-C"), self.user)

        self.assertEqual(RootAlias.objects.filter(owner=self.institution).count(), 0)
        # still creates a device keyed by the app uuid fallback
        self.assertEqual(
            SystemProperty.objects.filter(key="ereuse24", owner=self.institution).count(),
            1,
        )
