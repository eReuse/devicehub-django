import copy
import json

from django.conf import settings
from django.test import SimpleTestCase

from evidence.models import Evidence
from evidence.parse_details import ParseSnapshot

EXAMPLE_DIR = settings.BASE_DIR / "example"


def load(path):
    with open(EXAMPLE_DIR / path) as f:
        return json.load(f)


def storage_of(snapshot):
    return [
        c for c in ParseSnapshot(snapshot).components
        if c.get("type") == "Storage"
    ]


def drives_section(inxi):
    return next(v for n in inxi for k, v in n.items() if "Drives" in k)


class InxiStorageTests(SimpleTestCase):
    """inxi prints one row per disk followed, when smartctl ran, by a SMART
    row. A disk must not depend on that SMART row to be reported."""

    def setUp(self):
        # Two SATA SSDs, each with an ID row followed by a SMART row.
        # Drives rows: [summary, sda ID, sda SMART, sdb ID, sdb SMART]
        self.snapshot = load("snapshots/snapshot_workbench-script.json")
        self.inxi = json.loads(self.snapshot["data"]["inxi"])

    def _storage_with(self, inxi):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["data"]["inxi"] = json.dumps(inxi)
        return storage_of(snapshot)

    def test_disks_with_smart_data_are_complete(self):
        disks = self._storage_with(self.inxi)
        self.assertEqual(
            [d["cycles"] for d in disks], ["42929", "7006"])
        self.assertEqual(
            [d["health"] for d in disks], ["PASSED", "PASSED"])

    def test_disk_without_smart_row_is_still_reported(self):
        inxi = copy.deepcopy(self.inxi)
        del drives_section(inxi)[4]  # SMART row of the 2nd disk

        disks = self._storage_with(inxi)

        self.assertEqual(len(disks), 2)
        self.assertEqual(disks[1]["model"], "SSD 850 EVO mSATA 500GB")
        self.assertEqual(disks[1]["size"], "465.76 GiB")
        self.assertNotIn("cycles", disks[1])
        # the other disk keeps its own SMART data
        self.assertEqual(disks[0]["cycles"], "42929")

    def test_first_disk_without_smart_row_does_not_take_the_next_ones(self):
        inxi = copy.deepcopy(self.inxi)
        del drives_section(inxi)[2]  # SMART row of the 1st disk

        disks = self._storage_with(inxi)

        self.assertEqual(len(disks), 2)
        self.assertNotIn("cycles", disks[0])
        self.assertEqual(disks[1]["cycles"], "7006")

    def test_nvme_without_smartctl_is_reported(self):
        # Real snapshot: smartctl is not installed, so inxi has no SMART row.
        snapshot = load("demo-snapshots-vc/snapshot_pre-verifiable-credential.json")["data"]

        disks = storage_of(snapshot)

        self.assertEqual(len(disks), 1)
        self.assertEqual(disks[0]["model"], "MZVLW1T0HMLH-000L7")
        self.assertEqual(disks[0]["size"], "953.87 GiB")

    def test_smart_row_of_a_usb_disk_is_not_attached_to_another_disk(self):
        inxi = copy.deepcopy(self.inxi)
        drives_section(inxi).extend([
            {"002#0#2#type": "USB", "001#1#1#ID": "/dev/sdc",
             "003#0#2#serial": "USB123"},
            {"018#0#3#cycles": "5", "017#1#2#SMART": "yes",
             "019#0#3#health": "PASSED"},
        ])

        disks = self._storage_with(inxi)

        self.assertEqual(len(disks), 2)
        self.assertEqual([d["cycles"] for d in disks], ["42929", "7006"])

    def test_read_and_written_are_picked_up_from_sata_rows(self):
        disks = self._storage_with(self.inxi)

        self.assertEqual(disks[0]["read used"], "244.6 MiB")
        self.assertEqual(disks[0]["written used"], "258.9 MiB")
        self.assertEqual(disks[1]["written used"], "30.92 TiB")


class RamTotalTests(SimpleTestCase):
    """RamModule sizes come as text with a unit (inxi, lshw) or, in the old
    Workbench 11 format, as a bare number of MB."""

    def _total(self, sizes):
        ev = object.__new__(Evidence)  # no DB nor Xapian needed
        ev.doc = {}
        ev._export_components_memo = [
            {"type": "RamModule", "size": s} for s in sizes
        ]
        return ev.get_ram_total()

    def test_old_format_bare_numbers_are_mb(self):
        self.assertEqual(self._total([4096.0]), 4)
        self.assertEqual(self._total([4096.0, 4096.0]), 8)
        self.assertEqual(self._total([2048, 2048]), 4)

    def test_sizes_with_units_are_unchanged(self):
        self.assertEqual(self._total(["8 GiB", "8 GiB"]), 16)
        self.assertEqual(self._total(["4 GB"]), 4)
        self.assertEqual(self._total(["2048 MiB"]), 2)

    def test_old_format_sample_snapshot(self):
        # hp_probook_450.json has 2 x 4 GB; it used to be reported as 8192.
        snapshot = load("dpp-snapshots/hp_probook_450.json")
        ev = object.__new__(Evidence)
        ev.doc = snapshot
        ev._export_components_memo = ParseSnapshot(snapshot).components

        self.assertEqual(ev.get_ram_total(), 8)
