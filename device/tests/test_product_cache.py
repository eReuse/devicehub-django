import uuid as uuidlib
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.utils import timezone

from user.models import Institution
from evidence.models import SystemProperty
from device.models import Device, ProductCache


def _base_fields(**over):
    """A full evidence_export_fields() dict with all keys empty by default."""
    f = {
        'ID': '', 'manufacturer': '', 'model': '', 'serial': '',
        'cpu_model': '', 'cpu_cores': '', 'ram_total': '', 'ram_type': '',
        'ram_slots': '', 'slots_used': '', 'drive': '', 'gpu_model': '',
        'type': '', 'last_updated': '',
    }
    f.update(over)
    return f


def _device_with_evidences(per_uuid, shortid="ABC123"):
    """Build a Device that yields ``per_uuid[uuid]`` for each evidence.

    Skips __init__ (which hits the DB/Xapian) and wires merged_export_fields'
    dependencies: a fixed uuid list (newest first) and a per-evidence field map.
    A value of the sentinel ``RAISE`` makes evidence_export_fields raise for
    that uuid, simulating a missing/corrupt evidence.
    """
    d = Device.__new__(Device)
    d.uuids = list(per_uuid.keys())
    d.shortid = shortid
    d.last_evidence = None
    d.get_uuids = MagicMock()

    def fake_export():
        val = per_uuid[d.last_evidence]
        if val == "RAISE":
            raise KeyError("corrupt doc")
        return val

    d.evidence_export_fields = fake_export
    return d


class MergedExportFieldsTests(TestCase):
    """Unit tests for the newest-wins + backfill merge (no Xapian)."""

    def _merge(self, device):
        # Evidence(uuid) -> uuid identity, so last_evidence is the uuid key.
        with patch("device.models.Evidence", side_effect=lambda u: u):
            return device.merged_export_fields()

    def test_newest_wins_over_older(self):
        d = _device_with_evidences({
            "new": _base_fields(manufacturer="Dell", model="New"),
            "old": _base_fields(manufacturer="HP", model="Old"),
        })
        merged = self._merge(d)
        self.assertEqual(merged["manufacturer"], "Dell")
        self.assertEqual(merged["model"], "New")

    def test_missing_field_backfilled_from_older(self):
        d = _device_with_evidences({
            "new": _base_fields(manufacturer="Dell", cpu_model=""),
            "old": _base_fields(manufacturer="HP", cpu_model="i7-8550U"),
        })
        merged = self._merge(d)
        self.assertEqual(merged["manufacturer"], "Dell")     # newest kept
        self.assertEqual(merged["cpu_model"], "i7-8550U")    # backfilled

    def test_last_updated_never_backfilled(self):
        d = _device_with_evidences({
            "new": _base_fields(last_updated=""),
            "old": _base_fields(last_updated="2020-01-01T00:00:00"),
        })
        merged = self._merge(d)
        self.assertEqual(merged["last_updated"], "")  # newest's value, not older

    def test_zero_is_a_real_value_not_backfilled(self):
        d = _device_with_evidences({
            "new": _base_fields(slots_used=0),
            "old": _base_fields(slots_used=4),
        })
        merged = self._merge(d)
        self.assertEqual(merged["slots_used"], 0)

    def test_corrupt_newest_skipped_falls_back(self):
        d = _device_with_evidences({
            "bad": "RAISE",
            "good": _base_fields(manufacturer="HP"),
        })
        merged = self._merge(d)
        self.assertEqual(merged["manufacturer"], "HP")

    def test_all_evidence_fail_returns_minimal(self):
        d = _device_with_evidences({"bad1": "RAISE", "bad2": "RAISE"})
        merged = self._merge(d)
        self.assertEqual(merged, {"ID": "ABC123"})

    def test_non_legacy_websnapshot_empty_components_is_coherent(self):
        """A websnapshot (no parseable components) yields empty hardware
        getters: identity fields are populated and the hardware fields come
        back empty rather than garbage, so the projection stays coherent."""
        d = Device.__new__(Device)
        d.shortid = "WEB001"
        ev = MagicMock()
        ev.get_cpu_model.return_value = ""
        ev.get_cpu_cores.return_value = ""
        ev.get_ram_total.return_value = ""
        ev.get_ram_type.return_value = ""
        ev.get_ram_slots.return_value = ""
        ev.get_ram_slots_used.return_value = ""
        ev.get_drive.return_value = ""
        ev.get_gpu_model.return_value = ""
        d.last_evidence = ev
        d.get_last_evidence = lambda: None
        with patch.object(Device, "manufacturer", "WebMaker"), \
                patch.object(Device, "model", "WebModel"), \
                patch.object(Device, "serial_number", ""), \
                patch.object(Device, "type", "Laptop"), \
                patch.object(Device, "updated", ""):
            fields = d.evidence_export_fields()
        self.assertEqual(fields["manufacturer"], "WebMaker")
        self.assertEqual(fields["model"], "WebModel")
        self.assertEqual(fields["type"], "Laptop")
        # components parsed to nothing -> hardware stays empty, not garbage.
        self.assertEqual(fields["cpu_model"], "")
        self.assertEqual(fields["drive"], "")
        self.assertEqual(fields["ram_total"], "")

    def test_stops_reading_once_all_filled(self):
        d = _device_with_evidences({
            "new": _base_fields(manufacturer="Dell", model="M", serial="S",
                                 cpu_model="i7", cpu_cores="4", ram_total="8",
                                 ram_type="DDR4", ram_slots="2", slots_used="1",
                                 drive="SSD", gpu_model="Intel", type="Laptop",
                                 ID="X", last_updated="2021"),
            "old": _base_fields(manufacturer="HP"),
        })
        with patch("device.models.Evidence", side_effect=lambda u: u) as ev:
            d.merged_export_fields()
        # Newest already complete -> older evidence never constructed.
        self.assertEqual(ev.call_count, 1)


class RebuildTests(TestCase):
    """Unit tests for ProductCache.rebuild/drop/rebuild_all."""

    def setUp(self):
        self.inst = Institution.objects.create(name="Inst")

    def _patch_device(self, uuids, fields, storage=None):
        fake = MagicMock()
        fake.uuids = list(uuids)
        fake.merged_export_fields.return_value = fields
        fake.storage_readings.return_value = storage if storage is not None else {}
        return patch("device.models.Device", return_value=fake)

    def test_rebuild_creates_row_with_column_json_split(self):
        dt = timezone.now()
        fields = {
            "ID": "SHORT1", "type": "Laptop", "manufacturer": "Dell",
            "model": "Latitude", "serial": "SN1", "cpu_model": "i7",
            "last_updated": dt, "cpu_cores": "4", "ram_total": "8",
            "ram_type": "DDR4", "ram_slots": "2", "slots_used": "1",
            "drive": "SSD", "gpu_model": "Intel",
        }
        with self._patch_device(["u1"], fields):
            obj = ProductCache.rebuild(self.inst, "ereuse24:A")
        self.assertEqual(obj.shortid, "SHORT1")
        self.assertEqual(obj.type, "Laptop")
        self.assertEqual(obj.cpu_model, "i7")
        self.assertEqual(obj.last_updated, dt)
        self.assertEqual(obj.data, {
            "cpu_cores": "4", "ram_total": "8", "ram_type": "DDR4",
            "ram_slots": "2", "slots_used": "1", "drive": "SSD",
            "gpu_model": "Intel", "storage": {},
        })

    def test_rebuild_is_idempotent(self):
        fields = {"ID": "S", "type": "Laptop"}
        with self._patch_device(["u1"], fields):
            ProductCache.rebuild(self.inst, "ereuse24:A")
            ProductCache.rebuild(self.inst, "ereuse24:A")
        self.assertEqual(
            ProductCache.objects.filter(
                owner=self.inst, root="ereuse24:A").count(),
            1,
        )

    def test_rebuild_without_evidence_removes_stale_row(self):
        ProductCache.objects.create(
            owner=self.inst, root="ereuse24:A", shortid="OLD")
        with self._patch_device([], {}):
            result = ProductCache.rebuild(self.inst, "ereuse24:A")
        self.assertIsNone(result)
        self.assertFalse(
            ProductCache.objects.filter(
                owner=self.inst, root="ereuse24:A").exists())

    def test_empty_last_updated_stored_as_null(self):
        with self._patch_device(["u1"], {"ID": "S", "last_updated": ""}):
            obj = ProductCache.rebuild(self.inst, "ereuse24:A")
        self.assertIsNone(obj.last_updated)

    def test_rebuild_websnapshot_minimal_fields_is_coherent(self):
        """Non-legacy/websnapshot export shape (identity set, hardware empty)
        produces a coherent row: empty data fields, no exception."""
        fields = {
            "ID": "WEB001", "type": "Laptop", "manufacturer": "WebMaker",
            "model": "WebModel", "serial": "", "cpu_model": "",
            "last_updated": "",
        }
        with self._patch_device(["u1"], fields):
            obj = ProductCache.rebuild(self.inst, "ereuse24:W")
        self.assertEqual(obj.shortid, "WEB001")
        self.assertEqual(obj.manufacturer, "WebMaker")
        self.assertEqual(obj.cpu_model, "")
        expected = {k: "" for k in ProductCache.DATA_FIELDS}
        expected["storage"] = {}
        self.assertEqual(obj.data, expected)

    def test_rebuild_with_all_corrupt_evidence_writes_minimal_row(self):
        """When every evidence is missing/corrupt (search() -> None),
        merged_export_fields returns just {"ID": shortid}; rebuild must write a
        coherent minimal row, not raise."""
        with self._patch_device(["u1"], {"ID": "CORRUPT"}):
            obj = ProductCache.rebuild(self.inst, "ereuse24:C")
        self.assertIsNotNone(obj)
        self.assertEqual(obj.shortid, "CORRUPT")
        self.assertEqual(obj.type, "")
        self.assertEqual(obj.manufacturer, "")
        self.assertIsNone(obj.last_updated)

    def test_rebuild_into_existing_root_no_unique_violation(self):
        """A re-root collision: the gaining root already has a projection row.
        update_or_create must merge in place without violating unique(owner,
        root) and leave exactly one row."""
        ProductCache.objects.create(
            owner=self.inst, root="ereuse24:R", shortid="OLD")
        with self._patch_device(["u1"], {"ID": "NEW", "type": "Laptop"}):
            ProductCache.rebuild(self.inst, "ereuse24:R")
        rows = ProductCache.objects.filter(owner=self.inst, root="ereuse24:R")
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().shortid, "NEW")

    def test_drop_only_removes_target_root(self):
        ProductCache.objects.create(owner=self.inst, root="r1")
        ProductCache.objects.create(owner=self.inst, root="r2")
        ProductCache.drop(self.inst, "r1")
        self.assertFalse(
            ProductCache.objects.filter(owner=self.inst, root="r1").exists())
        self.assertTrue(
            ProductCache.objects.filter(owner=self.inst, root="r2").exists())

    def test_rebuild_stores_storage_readings_under_data(self):
        storage = {"S1": {"model": "Samsung", "manufacturer": "Samsung",
                          "size": "500 GB", "interface": "SATA",
                          "readings": [{"uuid": "u1", "power_on": "245d 7h",
                                        "power_on_hours": 5887}]}}
        with self._patch_device(["u1"], {"ID": "S"}, storage=storage):
            obj = ProductCache.rebuild(self.inst, "ereuse24:A")
        self.assertEqual(obj.data["storage"], storage)

    def test_rebuild_all_iterates_distinct_roots(self):
        # SystemProperty creation triggers the RootAlias self-reference signal.
        SystemProperty.objects.create(
            owner=self.inst, uuid=uuidlib.uuid4(), value="ereuse24:A")
        SystemProperty.objects.create(
            owner=self.inst, uuid=uuidlib.uuid4(), value="ereuse24:A")  # same root
        SystemProperty.objects.create(
            owner=self.inst, uuid=uuidlib.uuid4(), value="ereuse24:B")

        seen = []
        with patch.object(
            ProductCache, "rebuild",
            side_effect=lambda owner, root: seen.append(root),
        ):
            total = ProductCache.rebuild_all(owner=self.inst)

        self.assertEqual(total, 2)
        self.assertEqual(set(seen), {"ereuse24:A", "ereuse24:B"})


class StorageReadingsTests(TestCase):
    """Unit tests for Device.storage_readings (per-disk PoH history, no Xapian
    beyond the patched Evidence)."""

    def _device(self, uuids):
        d = Device.__new__(Device)
        d.uuids = list(uuids)
        d.get_uuids = MagicMock()
        return d

    def _evidence(self, created, components):
        ev = MagicMock()
        ev.created = created
        ev.get_components.return_value = components
        return ev

    def test_collects_readings_oldest_to_newest(self):
        evs = {
            "new": self._evidence("2025-02-01", [
                {"type": "Storage", "serialNumber": "S1", "model": "Samsung",
                 "manufacturer": "Samsung", "size": "500 GB",
                 "interface": "SATA", "time of used": "245d 7h",
                 "cycles": "1300", "health": "97%"},
            ]),
            "old": self._evidence("2025-01-01", [
                {"type": "Storage", "serialNumber": "S1", "model": "Samsung",
                 "manufacturer": "Samsung", "size": "500 GB",
                 "interface": "SATA", "time of used": "200d 0h",
                 "cycles": "1000", "health": "99%"},
            ]),
        }
        d = self._device(["new", "old"])  # newest first
        with patch("device.models.Evidence", side_effect=lambda u: evs[u]):
            disks = d.storage_readings()
        self.assertEqual(list(disks.keys()), ["S1"])
        readings = disks["S1"]["readings"]
        self.assertEqual([r["created"] for r in readings],
                         ["2025-01-01", "2025-02-01"])  # oldest -> newest
        self.assertEqual(readings[0]["power_on"], "200d 0h")
        self.assertEqual(readings[0]["power_on_hours"], 200 * 24)
        self.assertEqual(readings[1]["power_on_hours"], 245 * 24 + 7)

    def test_disk_swap_tracked_as_separate_serials(self):
        evs = {
            "new": self._evidence("2025-02-01", [
                {"type": "Storage", "serialNumber": "NEW",
                 "time of used": "10d 0h"},
            ]),
            "old": self._evidence("2025-01-01", [
                {"type": "Storage", "serialNumber": "OLD",
                 "time of used": "900d 0h"},
            ]),
        }
        d = self._device(["new", "old"])
        with patch("device.models.Evidence", side_effect=lambda u: evs[u]):
            disks = d.storage_readings()
        self.assertEqual(set(disks.keys()), {"OLD", "NEW"})
        self.assertEqual(len(disks["OLD"]["readings"]), 1)
        self.assertEqual(len(disks["NEW"]["readings"]), 1)

    def test_skips_non_storage_and_serialless(self):
        ev = self._evidence("2025-01-01", [
            {"type": "Processor", "serialNumber": "X"},
            {"type": "Storage", "serialNumber": "", "time of used": "5d"},
            {"type": "Storage", "serialNumber": "S2", "time of used": "5d 0h"},
        ])
        d = self._device(["u1"])
        with patch("device.models.Evidence", side_effect=lambda u: ev):
            disks = d.storage_readings()
        self.assertEqual(list(disks.keys()), ["S2"])

    def test_evidence_without_power_data_registers_disk_no_reading(self):
        ev = self._evidence("2025-01-01", [
            {"type": "Storage", "serialNumber": "S3", "model": "X"},
        ])
        d = self._device(["u1"])
        with patch("device.models.Evidence", side_effect=lambda u: ev):
            disks = d.storage_readings()
        self.assertEqual(disks["S3"]["readings"], [])
        self.assertEqual(disks["S3"]["model"], "X")

    def test_readings_are_json_serializable_uuid_as_str(self):
        import json
        u = uuidlib.uuid4()
        ev = self._evidence("2025-01-01", [
            {"type": "Storage", "serialNumber": "S5", "time of used": "1d 0h"},
        ])
        d = self._device([u])
        with patch("device.models.Evidence", side_effect=lambda x: ev):
            disks = d.storage_readings()
        reading = disks["S5"]["readings"][0]
        self.assertEqual(reading["uuid"], str(u))
        json.dumps(disks)  # must not raise

    def test_corrupt_evidence_skipped(self):
        good = self._evidence("2025-01-01", [
            {"type": "Storage", "serialNumber": "S4", "time of used": "1d 0h"},
        ])

        def factory(u):
            if u == "bad":
                raise KeyError("missing")
            return good

        d = self._device(["bad", "good"])
        with patch("device.models.Evidence", side_effect=factory):
            disks = d.storage_readings()
        self.assertEqual(list(disks.keys()), ["S4"])
