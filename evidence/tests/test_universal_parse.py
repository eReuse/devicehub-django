import json
import os
from unittest import mock

from django.test import SimpleTestCase, override_settings

from evidence import models
from evidence.models import Evidence
from evidence.sources import Sources, detect, WB11, LEGACY, INXI, DMI
from evidence.identity import parse_identity
from evidence.universal_parse import (
    Build,
    get_mac_win,
    get_mac_linux,
    _normalize_mac,
    _parse_pci_location,
    _parse_pci_bdf,
)
from evidence.universal_parse_details import ParseSnapshot


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SNAPSHOTS = os.path.join(REPO_ROOT, "example", "snapshots")
VC_SNAPSHOTS = os.path.join(REPO_ROOT, "example", "demo-snapshots-vc")


def load(path):
    with open(path) as f:
        return json.load(f)


class DetectFormatTests(SimpleTestCase):
    """detect() must classify every envelope by content signal, not version.

    The credential is no longer a branch: once Sources unwraps it, a signed VC
    falls into INXI like any regular workbench-script snapshot.
    """

    def test_detect_per_format(self):
        cases = [
            ("snapshot-workbench11.json", WB11),
            ("snapshot_workbench-script.json", INXI),
            ("snapshot_workbench-script_legacy.json", LEGACY),
            ("snapshot_windows.json", DMI),
        ]
        for name, expected in cases:
            with self.subTest(snapshot=name):
                sources = Sources(load(os.path.join(SNAPSHOTS, name)))
                self.assertEqual(detect(sources), expected)

    def test_detect_credential_unwraps_to_inxi(self):
        sources = Sources(
            load(os.path.join(VC_SNAPSHOTS, "snapshot_pre-verifiable-credential.json"))
        )
        self.assertEqual(detect(sources), INXI)

    def test_legacy_wins_over_device_when_lshw_present(self):
        # lshw/hwinfo must outrank a 'device' key (wb11 never carries lshw).
        sources = Sources({"data": {"lshw": "x"}, "device": {}})
        self.assertEqual(detect(sources), LEGACY)

    def test_detect_returns_none_when_no_signal(self):
        self.assertIsNone(detect(Sources({"data": {}})))


class SourcesEnvelopeTests(SimpleTestCase):
    """Sources resolves the three envelopes (plain, signed VC, nested
    DeviceSnapshotV1) into a single .data view, killing the 4 copies of
    'where is dmidecode?'.
    """

    def test_plain_envelope(self):
        src = Sources({"uuid": "u1", "data": {"dmidecode": "DMI"}})
        self.assertEqual(src.uuid, "u1")
        self.assertEqual(src.dmidecode, "DMI")

    def test_credential_envelope_collects_evidence(self):
        snap = {
            "credentialSubject": {"uuid": "vc1"},
            "evidence": [
                {"operation": "dmidecode", "output": "DMI"},
                {"operation": "smartctl", "output": "SMART"},
            ],
        }
        src = Sources(snap)
        self.assertEqual(src.uuid, "vc1")
        self.assertEqual(src.dmidecode, "DMI")
        self.assertEqual(src.smartctl, "SMART")

    def test_nested_devicesnapshot_is_unwrapped(self):
        snap = {"data": {"software": "wb", "uuid": "n1", "data": {"dmidecode": "DMI"}}}
        src = Sources(snap)
        self.assertEqual(src.uuid, "n1")
        self.assertEqual(src.dmidecode, "DMI")

    def test_inxi_string_is_json_decoded(self):
        src = Sources({"data": {"inxi": json.dumps([{"Machine": []}])}})
        self.assertEqual(src.inxi, [{"Machine": []}])

    def test_inxi_unparseable_returns_none(self):
        src = Sources({"uuid": "x", "data": {"inxi": "{not json"}})
        self.assertIsNone(src.inxi)


class MacHelperTests(SimpleTestCase):
    """The MAC pickers must return the most integrated NIC (lowest PCI
    location), normalized to lowercase colon format."""

    def test_normalize_mac(self):
        self.assertEqual(_normalize_mac("54-E1-AD-11-FB-B7"), "54:e1:ad:11:fb:b7")

    def test_parse_pci_bdf(self):
        self.assertEqual(_parse_pci_bdf("0000:00:1f.6"), (0, 0, 31, 6))
        self.assertIsNone(_parse_pci_bdf("lo"))

    def test_parse_pci_location_from_pnp_id(self):
        self.assertEqual(
            _parse_pci_location("PCI\\VEN_8086&DEV_1502\\3&b1bfb68&0&C8"),
            (0, 25, 0),
        )

    def test_get_mac_linux_prefers_lowest_bus(self):
        sysfs = (
            "0000:02:00.0 wlan0 aa:bb:cc:00:11:22\n"
            "0000:00:1f.6 enp0s31f6 54:e1:ad:11:fb:b7"
        )
        self.assertEqual(get_mac_linux(sysfs), "54:e1:ad:11:fb:b7")

    def test_get_mac_linux_skips_non_pci(self):
        self.assertIsNone(get_mac_linux("lo lo 00:00:00:00:00:00"))

    def test_get_mac_win_prefers_lowest_location(self):
        adapters = [
            {
                "PnPDeviceID": "PCI\\VEN_8086&DEV_1502\\3&b1bfb68&0&C8",
                "PermanentAddress": "54E1AD11FBB7",
            },
            {
                "PnPDeviceID": "PCI\\VEN_8086&DEV_0085\\longwifiid",
                "MacAddress": "AA-BB-CC-DD-EE-FF",
            },
        ]
        self.assertEqual(get_mac_win(adapters), "54:e1:ad:11:fb:b7")

    def test_get_mac_win_empty(self):
        self.assertIsNone(get_mac_win([]))


class ParseIdentityTests(SimpleTestCase):
    """parse_identity is dmidecode-first with native/inxi fallbacks, and
    normalizes (lower + strip + no spaces) so every format yields the same HID
    seed."""

    def test_identity_from_windows_dmidecode(self):
        sources = Sources(load(os.path.join(SNAPSHOTS, "snapshot_windows.json")))
        identity = parse_identity(sources, native_device=sources.device)
        self.assertEqual(
            identity,
            {
                "manufacturer": "hewlett-packard",
                "model": "hpelitebook2570p",
                "serial_number": "cnu4069y46",
            },
        )

    def test_identity_falls_back_to_native_device(self):
        sources = Sources({"data": {}})
        native = {"manufacturer": "Dell", "model": "X1", "serialNumber": "S1"}
        self.assertEqual(
            parse_identity(sources, native_device=native),
            {"manufacturer": "dell", "model": "x1", "serial_number": "s1"},
        )

    def test_identity_empty_without_any_source(self):
        self.assertEqual(parse_identity(Sources({"data": {}})), {})


class UniversalParseWindowsTests(SimpleTestCase):
    """End-to-end build of the Windows (dmidecode-only) snapshot: device
    identity, the ereuse24 HID, and the component set."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.snap = load(os.path.join(SNAPSHOTS, "snapshot_windows.json"))

    def test_build_device_identity(self):
        build = Build(self.snap)
        self.assertEqual(build.manufacturer, "Hewlett-Packard")
        self.assertEqual(build.model, "HP EliteBook 2570p")
        self.assertEqual(build.serial_number, "CNU4069Y46")
        self.assertEqual(build.chassis, "notebook")
        self.assertEqual(build.sku, "A1L17AV")

    def test_build_mac_from_get_netadapter(self):
        # The Windows command is 'get-netadapter'; its output feeds the MAC.
        build = Build(self.snap)
        self.assertEqual(build.mac, "fc:15:b4:e8:53:61")

    def test_build_hid_ereuse24(self):
        build = Build(self.snap)
        self.assertIn("ereuse24", build.algorithms)
        self.assertEqual(
            build.get_hid("ereuse24"),
            "Hewlett-PackardHP EliteBook 2570pnotebookCNU4069Y46fc:15:b4:e8:53:61",
        )

    @override_settings(DEVICEHUB_ALGORITHM_DEVICE="ereuse26")
    def test_build_hid_ereuse26_normalizes_identity(self):
        build = Build(self.snap)
        self.assertIn("ereuse26", build.algorithms)
        # ereuse26 = manufacturer + model + serial_number + mac (no chassis),
        # over the normalized identity.
        self.assertEqual(
            build.get_hid("ereuse26"),
            "hewlett-packardhpelitebook2570pcnu4069y46fc:15:b4:e8:53:61",
        )

    def test_build_components(self):
        build = Build(self.snap)
        build._get_components()
        types = sorted(c["type"] for c in build.components)
        self.assertEqual(
            types,
            [
                "Battery",
                "Motherboard",
                "Processor",
                "RamModule",
                "RamModule",
                "SolidStateDrive",
                "SolidStateDrive",
            ],
        )
        for c in build.components:
            self.assertNotIn("actions", c)
        self.assertNotIn("actions", build.device)


class UniversalParseDetailsTests(SimpleTestCase):
    """ParseSnapshot builds the full device + components from dmidecode/smartctl
    for evidence.models (read-time)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.parsed = ParseSnapshot(load(os.path.join(SNAPSHOTS, "snapshot_windows.json")))

    def test_device_fields(self):
        device = self.parsed.device
        self.assertEqual(device["manufacturer"], "Hewlett-Packard")
        self.assertEqual(device["model"], "HP EliteBook 2570p")
        self.assertEqual(device["serialNumber"], "CNU4069Y46")
        self.assertEqual(device["type"], "Laptop")
        self.assertEqual(device["system_uuid"], "68f4574e-1a43-11e2-8078-8b0dda07006b")

    def test_processor_component(self):
        cpu = next(c for c in self.parsed.components if c["type"] == "Processor")
        self.assertEqual(cpu["manufacturer"], "Intel(R) Corporation")
        self.assertEqual(cpu["cores"], 2)
        self.assertEqual(cpu["threads"], 4)
        self.assertEqual(cpu["address"], 64)

    def test_storage_split_manufacturer_model(self):
        ssd = next(c for c in self.parsed.components if c["type"] == "SolidStateDrive")
        self.assertTrue(ssd["model"])
        self.assertIn("interface", ssd)

    def test_triple_newline_dmidecode_is_normalized(self):
        # dmidecode 3.6 on Windows emits \n\n\n which shifts DMIParse's index;
        # the parser must collapse it and still find the System block.
        raw = load(os.path.join(SNAPSHOTS, "snapshot_windows.json"))["data"]["dmidecode"]
        parsed = ParseSnapshot({"data": {"dmidecode": "\n\n\n" + raw}})
        self.assertEqual(parsed.device["manufacturer"], "Hewlett-Packard")


class _FakeDoc:
    def __init__(self, doc):
        self._doc = doc

    def get_data(self):
        return json.dumps(self._doc)


class _FakeMatch:
    def __init__(self, doc):
        self.document = _FakeDoc(doc)


class _FakeMatches(list):
    def size(self):
        return len(self)


def _windows_evidence():
    """Build an Evidence whose Xapian doc is the Windows snapshot, without
    touching the DB or the Xapian index."""
    doc = load(os.path.join(SNAPSHOTS, "snapshot_windows.json"))
    with mock.patch.object(Evidence, "get_owner", lambda self: None), \
         mock.patch.object(Evidence, "get_time", lambda self: None), \
         mock.patch.object(models, "search",
                           return_value=_FakeMatches([_FakeMatch(doc)])):
        ev = Evidence(doc["uuid"])
        ev.get_doc()
    return ev


class EvidenceReadTimeWindowsTests(SimpleTestCase):
    """A dmi-only (Windows) snapshot must render and export through the
    read path. If any getter still assumes inxi, the device's record/export
    would break; this pins that every field resolves via the dmi branch.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ev = _windows_evidence()

    def test_format_flags_route_to_dmi(self):
        # dmi-only: not legacy/beta/web, and no inxi parsed.
        self.assertFalse(self.ev.is_legacy())
        self.assertFalse(self.ev.is_beta())
        self.assertFalse(self.ev.is_web_snapshot())
        self.assertIsNone(self.ev.inxi)
        self.assertIsNotNone(self.ev.dmi)

    def test_identity_getters(self):
        self.assertEqual(self.ev.get_manufacturer(), "Hewlett-Packard")
        self.assertEqual(self.ev.get_model(), "HP EliteBook 2570p")
        self.assertEqual(self.ev.get_serial_number(), "CNU4069Y46")
        self.assertEqual(self.ev.get_chassis(), "Laptop")
        self.assertEqual(self.ev.get_version(), "A1029C1102")

    def test_export_getters(self):
        self.assertEqual(
            self.ev.get_cpu_model(), "Intel(R) Core(TM) i7-3520M CPU @ 2.90GHz"
        )
        self.assertEqual(self.ev.get_cpu_cores(), 2)
        self.assertEqual(self.ev.get_ram_total(), 8)
        self.assertEqual(self.ev.get_ram_type(), "DDR3")
        self.assertEqual(self.ev.get_ram_slots(), 2)
        self.assertIn("480103981056", self.ev.get_drive())

    def test_components_parsed(self):
        self.assertEqual(len(self.ev.get_components()), 7)
