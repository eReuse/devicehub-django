import uuid

from django.test import TestCase

from user.models import Institution, User
from evidence.parse import Build
from evidence.models import SystemProperty, UserProperty, RootAlias


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
                "security_patch": "2026-08-05",
            },
            "usage": {
                "battery_cycle_count": 150,
                "boot_count": 80,
                "uptime_hours": 12,
                "device_age_days": 600,
            },
            "hwtest": {
                "verdict": "OK",
                "results": [
                    {"id": "screen", "status": "PASS"},
                    {"id": "touch", "status": "PASS"},
                    {"id": "charging", "status": "SKIP", "note": "no charger at hand"},
                ],
            },
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

    def test_hwtest_results_become_user_properties(self):
        snap = mobile_snapshot("AUCOOP-HW")
        Build(snap, self.user)

        props = {
            p.key: p.value
            for p in UserProperty.objects.filter(
                device_id="custom_id:{}".format(snap["data"]["device"]["manual_id"]),
                owner=self.institution,
                type=UserProperty.Type.USER,
            )
        }
        self.assertEqual(props.get("hwtest:verdict"), "OK")
        self.assertEqual(props.get("hwtest:screen"), "PASS")
        self.assertEqual(props.get("hwtest:touch"), "PASS")
        self.assertEqual(props.get("hwtest:charging"), "SKIP")
        self.assertEqual(props.get("hwtest:charging:note"), "no charger at hand")
        self.assertNotIn("hwtest:screen:note", props)

    def test_android_os_data_become_user_properties(self):
        snap = mobile_snapshot("AUCOOP-OS")
        Build(snap, self.user)

        props = {
            p.key: p.value
            for p in UserProperty.objects.filter(
                device_id="custom_id:{}".format(snap["data"]["device"]["manual_id"]),
                owner=self.institution,
                type=UserProperty.Type.USER,
            )
        }
        self.assertEqual(props.get("android:version"), "15")
        self.assertEqual(props.get("android:api_level"), "35")
        self.assertEqual(props.get("android:security_patch"), "2026-08-05")

    def test_power_on_hours_estimated_into_user_property(self):
        snap = mobile_snapshot("AUCOOP-POH")
        Build(snap, self.user)

        props = {
            p.key: p.value
            for p in UserProperty.objects.filter(
                device_id="custom_id:{}".format(snap["data"]["device"]["manual_id"]),
                owner=self.institution,
                type=UserProperty.Type.USER,
            )
        }
        # 150 cycles * 18 h/cycle = 2700 (battery_cycle wins over weaker signals)
        self.assertEqual(props.get("usage:power_on_hours"), "2700")
        self.assertEqual(props.get("usage:power_on_hours_method"), "battery_cycle")
        self.assertEqual(props.get("usage:power_on_hours_confidence"), "MEDIUM")
        self.assertEqual(props.get("usage:power_on_hours_estimator"), "usage_chain_v1")

    def test_reestimate_command_applies_another_estimator(self):
        from io import StringIO

        from django.core.management import call_command

        from action.models import DeviceLog
        from evidence.tests.test_estimators import SignalsTestEstimator  # registers test_signals_v0

        snap = mobile_snapshot("AUCOOP-REEST")
        snap["data"]["signals"] = {"test_hours": 12345}
        Build(snap, self.user)

        out = StringIO()
        call_command("reestimate_mobile_poh", "--estimator", SignalsTestEstimator.name, stdout=out)

        props = {
            p.key: p.value
            for p in UserProperty.objects.filter(
                owner=self.institution, device_id="custom_id:AUCOOP-REEST", type=UserProperty.Type.USER
            )
        }
        self.assertEqual(props.get("usage:power_on_hours"), "12345")
        self.assertEqual(props.get("usage:power_on_hours_estimator"), "test_signals_v0")
        self.assertTrue(
            DeviceLog.objects.filter(
                snapshot_uuid=snap["uuid"], event="usage:power_on_hours: 2700 → 12345"
            ).exists()
        )

        # Running it again changes nothing.
        out = StringIO()
        call_command("reestimate_mobile_poh", "--estimator", SignalsTestEstimator.name, stdout=out)
        self.assertIn("Changed 0 properties", out.getvalue())

    def test_no_manual_id_no_alias(self):
        Build(mobile_snapshot(None, app_uuid="uuid-C"), self.user)

        # only the self-referential row every SystemProperty gets; no custom_id link
        aliases = RootAlias.objects.filter(owner=self.institution)
        self.assertEqual(aliases.count(), 1)
        self.assertEqual(aliases.first().root, aliases.first().alias)
        # still creates a device keyed by the app uuid fallback
        self.assertEqual(
            SystemProperty.objects.filter(key="ereuse24", owner=self.institution).count(),
            1,
        )

    def test_properties_show_on_product_page(self):
        from device.models import Device

        Build(mobile_snapshot("AUCOOP-PAGE"), self.user)

        device = Device(id="custom_id:AUCOOP-PAGE", owner=self.institution)
        props = {p.key: p.value for p in device.get_user_properties()}
        self.assertEqual(props.get("hwtest:verdict"), "OK")
        self.assertEqual(props.get("hwtest:screen"), "PASS")
        self.assertEqual(props.get("usage:power_on_hours"), "2700")

    def test_rescan_updates_product_value_and_logs_change(self):
        from action.models import DeviceLog

        Build(mobile_snapshot("AUCOOP-RESCAN"), self.user)
        second = mobile_snapshot("AUCOOP-RESCAN")
        second["data"]["hwtest"]["results"][0]["status"] = "FAIL"
        Build(second, self.user)

        current = UserProperty.objects.filter(
            owner=self.institution,
            device_id="custom_id:AUCOOP-RESCAN",
            key="hwtest:screen",
        )
        self.assertEqual(current.count(), 1)
        self.assertEqual(current.first().value, "FAIL")
        self.assertTrue(
            DeviceLog.objects.filter(
                snapshot_uuid=second["uuid"], event="hwtest:screen: PASS → FAIL"
            ).exists()
        )

    def test_rescan_removes_values_no_longer_reported(self):
        from action.models import DeviceLog
        from device.models import Device

        Build(mobile_snapshot("AUCOOP-STALE"), self.user)
        second = mobile_snapshot("AUCOOP-STALE")
        second["data"]["hwtest"]["results"][2] = {"id": "charging", "status": "PASS"}
        Build(second, self.user)

        device = Device(id="custom_id:AUCOOP-STALE", owner=self.institution)
        props = {p.key: p.value for p in device.get_user_properties()}
        self.assertEqual(props.get("hwtest:charging"), "PASS")
        self.assertNotIn("hwtest:charging:note", props)
        self.assertTrue(
            DeviceLog.objects.filter(
                snapshot_uuid=second["uuid"],
                event="hwtest:charging:note: no charger at hand → (removed)",
            ).exists()
        )

    def test_rescan_without_block_keeps_its_values(self):
        # A snapshot that does not carry a block (e.g. inventory without
        # hwtest) says nothing about it: previous values stay.
        from device.models import Device

        Build(mobile_snapshot("AUCOOP-PARTIAL"), self.user)
        second = mobile_snapshot("AUCOOP-PARTIAL")
        del second["data"]["hwtest"]
        Build(second, self.user)

        device = Device(id="custom_id:AUCOOP-PARTIAL", owner=self.institution)
        props = {p.key: p.value for p in device.get_user_properties()}
        self.assertEqual(props.get("hwtest:screen"), "PASS")
        self.assertEqual(props.get("hwtest:charging:note"), "no charger at hand")

    def test_properties_are_only_stored_on_the_product(self):
        # USER properties are keyed by product (device_id), never by evidence.
        snap = mobile_snapshot("AUCOOP-ONLY-PRODUCT")
        Build(snap, self.user)
        Build(mobile_snapshot("AUCOOP-ONLY-PRODUCT"), self.user)

        self.assertFalse(
            UserProperty.objects.filter(owner=self.institution, device_id=None).exists()
        )
        self.assertEqual(
            UserProperty.objects.filter(
                owner=self.institution,
                device_id="custom_id:AUCOOP-ONLY-PRODUCT",
                key="hwtest:screen",
            ).count(),
            1,
        )

    def test_other_parsers_do_not_accept_device_under_data(self):
        # data.device is the Android shape only; the shared check is unchanged.
        snap = mobile_snapshot("AUCOOP-OTHER")
        snap["software"] = "workbench"
        with self.assertRaises(Exception):
            Build(snap, self.user)
