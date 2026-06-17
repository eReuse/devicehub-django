import csv
import io
import uuid as uuidlib
from unittest.mock import patch

from django.test import TestCase, RequestFactory

from user.models import Institution, User
from evidence.models import SystemProperty, UserProperty
from device.product_cache import ProductCache
from action.models import State, StateDefinition
from lot.models import (
    Lot, LotTag, LotSubscription, Beneficiary, DeviceBeneficiary,
)
from dashboard.views import (
    LotDashboardView, AllDevicesView, UnassignedDevicesView,
)


class LotExportTests(TestCase):
    """create_export reads the ProductCache read model and batches the
    relational fields; it must never touch Xapian per device."""

    def setUp(self):
        self.institution = Institution.objects.create(name="Inst")
        self.user = User.objects.create(
            email="u@test.local", institution=self.institution)
        self.tag = LotTag.objects.create(name="t", owner=self.institution)
        self.lot = Lot.objects.create(
            name="L", owner=self.institution, type=self.tag)

        self.uuids = {}
        for v in ["ereuse24:aaaaaa", "ereuse24:bbbbbb"]:
            sp = SystemProperty.objects.create(
                owner=self.institution, uuid=uuidlib.uuid4(), value=v)
            self.uuids[v] = sp.uuid
            self.lot.add(v)

    def _view(self, query=""):
        req = RequestFactory().get("/", {"q": query} if query else {})
        req.user = self.user
        view = LotDashboardView()
        view.request = req
        view.kwargs = {"pk": self.lot.pk}
        return view

    def _rows(self, response):
        text = response.content.decode()
        reader = csv.DictReader(io.StringIO(text))
        return {row["ID"]: row for row in reader}

    def test_export_does_not_touch_xapian(self):
        view = self._view()
        with patch("evidence.xapian.search") as s, \
                patch("evidence.xapian.index") as i:
            response = view.create_export("csv")
        s.assert_not_called()
        i.assert_not_called()
        self.assertEqual(len(self._rows(response)), 2)

    def test_export_ids_come_from_projection_shortid(self):
        rows = self._rows(self._view().create_export("csv"))
        self.assertEqual(set(rows), {"AAAAAA", "BBBBBB"})

    def test_beneficiary_status_defaults_to_available(self):
        rows = self._rows(self._view().create_export("csv"))
        self.assertEqual(rows["AAAAAA"]["beneficiary_status"], "Available")

    def test_beneficiary_status_reflects_devicebeneficiary_row(self):
        shop = LotSubscription.objects.create(
            lot=self.lot, user=self.user, type=LotSubscription.Type.SHOP)
        b = Beneficiary.objects.create(
            lot=self.lot, shop=shop, email="b@test.local")
        DeviceBeneficiary.objects.create(
            beneficiary=b, device_id="ereuse24:aaaaaa",
            status=DeviceBeneficiary.Status.CONFIRMED)

        rows = self._rows(self._view().create_export("csv"))
        self.assertEqual(rows["AAAAAA"]["beneficiary_status"], "Confirmed")
        self.assertEqual(rows["BBBBBB"]["beneficiary_status"], "Available")

    def test_current_state_from_latest_evidence_uuid(self):
        StateDefinition.objects.create(
            institution=self.institution, state="Repaired", order=1)
        State.objects.create(
            institution=self.institution, user=self.user,
            state="Repaired", snapshot_uuid=self.uuids["ereuse24:aaaaaa"])

        rows = self._rows(self._view().create_export("csv"))
        self.assertEqual(rows["AAAAAA"]["current_state"], "Repaired")
        self.assertEqual(rows["BBBBBB"]["current_state"], "")

    def test_user_properties_concatenated(self):
        UserProperty.objects.create(
            owner=self.institution, device_id="ereuse24:aaaaaa",
            key="color", value="blue", type=UserProperty.Type.USER)

        rows = self._rows(self._view().create_export("csv"))
        self.assertEqual(rows["AAAAAA"]["user_properties"], "(color:blue) ")


class _GoldenDevice:
    """Deterministic stand-in for Device so the projection (and thus the
    export) carries fixed hardware values, making a byte-exact golden possible
    without a populated Xapian."""

    _FIELDS = {
        "ereuse24:aaaaaa": {
            "ID": "AAAAAA", "type": "Laptop", "manufacturer": "Dell",
            "model": "Latitude", "serial": "SN-A", "cpu_model": "i7",
            "last_updated": "", "cpu_cores": "4", "ram_total": "8",
            "ram_type": "DDR4", "ram_slots": "2", "slots_used": "1",
            "drive": "SSD", "gpu_model": "Intel",
        },
        "ereuse24:bbbbbb": {
            "ID": "BBBBBB", "type": "Laptop", "manufacturer": "HP",
            "model": "EliteBook", "serial": "SN-B", "cpu_model": "i5",
            "last_updated": "", "cpu_cores": "2", "ram_total": "16",
            "ram_type": "DDR4", "ram_slots": "2", "slots_used": "2",
            "drive": "NVMe", "gpu_model": "AMD",
        },
    }

    def __init__(self, id, owner):
        self.id = id
        self.owner = owner
        self.uuids = []

    def get_uuids(self):
        from evidence.models import RootAlias
        aliases = RootAlias.physical_aliases(self.owner, self.id)
        self.uuids = list(
            SystemProperty.objects
            .filter(owner=self.owner, value__in=aliases)
            .values_list("uuid", flat=True))

    def merged_export_fields(self):
        return dict(self._FIELDS[self.id])

    def storage_readings(self):
        return {}


class LotExportGoldenTests(TestCase):
    """Byte-exact regression lock for the lot CSV export (Tasks 1 and 6).

    Rows from distinct() have no guaranteed order, so the header is compared
    byte-for-byte and the data rows are compared as a sorted set of exact
    lines: every field of every row is locked, order is not."""

    GOLDEN_HEADER = (
        "ID,type,manufacturer,model,cpu_model,cpu_cores,current_state,"
        "ram_total,ram_type,ram_slots,slots_used,drive,gpu_model,"
        "user_properties,serial,last_updated,beneficiary_status"
    )
    GOLDEN_ROWS = sorted([
        "AAAAAA,Laptop,Dell,Latitude,i7,4,Repaired,8,DDR4,2,1,SSD,Intel,"
        "(color:blue) ,SN-A,,Available",
        "BBBBBB,Laptop,HP,EliteBook,i5,2,,16,DDR4,2,2,NVMe,AMD,,SN-B,,Confirmed",
    ])

    def setUp(self):
        patcher = patch("device.models.Device", side_effect=_GoldenDevice)
        self.addCleanup(patcher.stop)
        patcher.start()

        self.institution = Institution.objects.create(name="Inst")
        self.user = User.objects.create(
            email="u@test.local", institution=self.institution)
        self.tag = LotTag.objects.create(name="t", owner=self.institution)
        self.lot = Lot.objects.create(
            name="L", owner=self.institution, type=self.tag)

        self.uuids = {}
        for v in ["ereuse24:aaaaaa", "ereuse24:bbbbbb"]:
            sp = SystemProperty.objects.create(
                owner=self.institution, uuid=uuidlib.uuid4(), value=v)
            self.uuids[v] = sp.uuid
            self.lot.add(v)

        # current_state for device A only.
        StateDefinition.objects.create(
            institution=self.institution, state="Repaired", order=1)
        State.objects.create(
            institution=self.institution, user=self.user,
            state="Repaired", snapshot_uuid=self.uuids["ereuse24:aaaaaa"])

        # a user property on device A.
        UserProperty.objects.create(
            owner=self.institution, device_id="ereuse24:aaaaaa",
            key="color", value="blue", type=UserProperty.Type.USER)

        # device B confirmed to a beneficiary.
        shop = LotSubscription.objects.create(
            lot=self.lot, user=self.user, type=LotSubscription.Type.SHOP)
        b = Beneficiary.objects.create(
            lot=self.lot, shop=shop, email="b@test.local")
        DeviceBeneficiary.objects.create(
            beneficiary=b, device_id="ereuse24:bbbbbb",
            status=DeviceBeneficiary.Status.CONFIRMED)

    def _view(self):
        req = RequestFactory().get("/")
        req.user = self.user
        view = LotDashboardView()
        view.request = req
        view.kwargs = {"pk": self.lot.pk}
        return view

    def test_export_csv_matches_golden(self):
        response = self._view().create_export("csv")
        lines = response.content.decode().splitlines()
        self.assertEqual(lines[0], self.GOLDEN_HEADER)
        self.assertEqual(sorted(lines[1:]), self.GOLDEN_ROWS)


class LotTableDataTests(TestCase):
    """get_table_data builds list-view rows from the ProductCache read
    model and batched relational queries, with no per-device Xapian access."""

    def setUp(self):
        self.institution = Institution.objects.create(name="Inst")
        self.user = User.objects.create(
            email="u@test.local", institution=self.institution)
        self.tag = LotTag.objects.create(name="t", owner=self.institution)
        self.lot = Lot.objects.create(
            name="L", owner=self.institution, type=self.tag)
        self.uuids = {}
        for v in ["ereuse24:aaaaaa", "ereuse24:bbbbbb"]:
            sp = SystemProperty.objects.create(
                owner=self.institution, uuid=uuidlib.uuid4(), value=v)
            self.uuids[v] = sp.uuid
            self.lot.add(v)

    def _view(self, **params):
        req = RequestFactory().get("/", params)
        req.user = self.user
        view = LotDashboardView()
        view.request = req
        view.kwargs = {"pk": self.lot.pk}
        view.object = self.lot
        return view

    def test_table_data_does_not_touch_xapian(self):
        view = self._view()
        with patch("evidence.xapian.search") as s, \
                patch("evidence.xapian.index") as i:
            rows = view.get_table_data()
        s.assert_not_called()
        i.assert_not_called()
        self.assertEqual(len(rows), 2)

    def test_rows_carry_projection_shortid_and_link_pk(self):
        rows = {r['id']: r for r in self._view().get_table_data()}
        self.assertEqual(
            rows['ereuse24:aaaaaa']['shortid'], "AAAAAA")
        # link target is the canonical root itself.
        self.assertEqual(
            rows['ereuse24:aaaaaa']['link_pk'], 'ereuse24:aaaaaa')

    def test_current_state_resolved_per_device(self):
        StateDefinition.objects.create(
            institution=self.institution, state="Repaired", order=1)
        State.objects.create(
            institution=self.institution, user=self.user,
            state="Repaired", snapshot_uuid=self.uuids["ereuse24:aaaaaa"])

        rows = {r['id']: r for r in self._view().get_table_data()}
        self.assertEqual(rows['ereuse24:aaaaaa']['current_state'], "Repaired")
        self.assertEqual(rows['ereuse24:bbbbbb']['current_state'], '--')

    def test_sort_by_current_state(self):
        StateDefinition.objects.create(
            institution=self.institution, state="Repaired", order=1)
        State.objects.create(
            institution=self.institution, user=self.user,
            state="Repaired", snapshot_uuid=self.uuids["ereuse24:bbbbbb"])

        rows = self._view(sort="current_state").get_table_data()
        # Device with a state sorts ahead of the one whose state is None.
        self.assertEqual(rows[0]['id'], 'ereuse24:bbbbbb')


class ProductCacheDeviceListTests(TestCase):
    """AllDevicesView / UnassignedDevicesView build their table rows from the
    ProductCache read model plus batched relational queries, with no
    per-device Device construction (and thus no Xapian read/parse per row)."""

    def setUp(self):
        self.institution = Institution.objects.create(name="Inst")
        self.user = User.objects.create(
            email="u@test.local", institution=self.institution)
        self.tag = LotTag.objects.create(name="t", owner=self.institution)
        self.uuids = {}
        for v in ["ereuse24:aaaaaa", "ereuse24:bbbbbb"]:
            sp = SystemProperty.objects.create(
                owner=self.institution, uuid=uuidlib.uuid4(), value=v)
            self.uuids[v] = sp.uuid

    def _view(self, cls, **params):
        req = RequestFactory().get("/", params)
        req.user = self.user
        view = cls()
        view.request = req
        return view

    def test_all_devices_ids_and_count(self):
        view = self._view(AllDevicesView)
        root_ids, count = view.get_device_ids()
        self.assertEqual(count, 2)
        self.assertEqual(
            set(root_ids), {"ereuse24:aaaaaa", "ereuse24:bbbbbb"})

    def test_rows_carry_projection_shortid_and_link_pk(self):
        view = self._view(AllDevicesView)
        rows = {r['id']: r for r in view.build_product_cache_rows(
            ["ereuse24:aaaaaa", "ereuse24:bbbbbb"])}
        self.assertEqual(rows['ereuse24:aaaaaa']['shortid'], "AAAAAA")
        self.assertEqual(rows['ereuse24:aaaaaa']['link_pk'], 'ereuse24:aaaaaa')

    def test_list_does_not_touch_xapian(self):
        view = self._view(AllDevicesView)
        with patch("evidence.xapian.search") as s, \
                patch("evidence.xapian.index") as i:
            root_ids, _ = view.get_device_ids()
            rows = view.build_product_cache_rows(list(root_ids))
        s.assert_not_called()
        i.assert_not_called()
        self.assertEqual(len(rows), 2)

    def test_current_state_resolved_per_device(self):
        StateDefinition.objects.create(
            institution=self.institution, state="Repaired", order=1)
        State.objects.create(
            institution=self.institution, user=self.user,
            state="Repaired", snapshot_uuid=self.uuids["ereuse24:aaaaaa"])

        view = self._view(AllDevicesView)
        rows = {r['id']: r for r in view.build_product_cache_rows(
            ["ereuse24:aaaaaa", "ereuse24:bbbbbb"])}
        self.assertEqual(rows['ereuse24:aaaaaa']['current_state'], "Repaired")
        self.assertEqual(rows['ereuse24:bbbbbb']['current_state'], '--')

    def test_inbox_excludes_assigned_devices(self):
        lot = Lot.objects.create(
            name="L", owner=self.institution, type=self.tag)
        lot.add("ereuse24:aaaaaa")

        view = self._view(UnassignedDevicesView)
        root_ids, count = view.get_device_ids()
        self.assertEqual(count, 1)
        self.assertEqual(root_ids, ["ereuse24:bbbbbb"])

    def _set_projection(self, root, **fields):
        ProductCache.objects.update_or_create(
            owner=self.institution, root=root, defaults=fields)

    def test_sort_by_manufacturer_replaces_default_order(self):
        self._set_projection("ereuse24:aaaaaa", manufacturer="Zeta")
        self._set_projection("ereuse24:bbbbbb", manufacturer="Alpha")

        view = self._view(AllDevicesView, sort="manufacturer")
        root_ids, _ = view.get_device_ids()
        self.assertEqual(root_ids, ["ereuse24:bbbbbb", "ereuse24:aaaaaa"])

        view = self._view(AllDevicesView, sort="-manufacturer")
        root_ids, _ = view.get_device_ids()
        self.assertEqual(root_ids, ["ereuse24:aaaaaa", "ereuse24:bbbbbb"])

    def test_sort_by_type_orders_by_projection_column(self):
        self._set_projection("ereuse24:aaaaaa", type="Server")
        self._set_projection("ereuse24:bbbbbb", type="Laptop")

        view = self._view(AllDevicesView, sort="type")
        root_ids, _ = view.get_device_ids()
        self.assertEqual(root_ids, ["ereuse24:bbbbbb", "ereuse24:aaaaaa"])

    def test_sort_applies_to_inbox_too(self):
        self._set_projection("ereuse24:aaaaaa", model="M2")
        self._set_projection("ereuse24:bbbbbb", model="M1")

        view = self._view(UnassignedDevicesView, sort="model")
        root_ids, _ = view.get_device_ids()
        self.assertEqual(root_ids, ["ereuse24:bbbbbb", "ereuse24:aaaaaa"])

    def test_unknown_sort_keeps_default_latest_order(self):
        # default order is -latest: the most recently seen root comes first
        # (bbbbbb's SystemProperty was created after aaaaaa's in setUp).
        view = self._view(AllDevicesView, sort="bogus")
        root_ids, _ = view.get_device_ids()
        self.assertEqual(root_ids, ["ereuse24:bbbbbb", "ereuse24:aaaaaa"])


class LotSortTests(TestCase):
    """LotDashboardView orders its rows from the ProductCache columns in
    Python (lots are bounded). type/manufacturer/model are sortable like the
    All Devices / Inbox lists; the user sort replaces the default
    -last_updated order."""

    def setUp(self):
        self.institution = Institution.objects.create(name="Inst")
        self.user = User.objects.create(
            email="u@test.local", institution=self.institution)
        self.tag = LotTag.objects.create(name="t", owner=self.institution)
        self.lot = Lot.objects.create(
            name="L", owner=self.institution, type=self.tag)
        for v in ["ereuse24:aaaaaa", "ereuse24:bbbbbb"]:
            SystemProperty.objects.create(
                owner=self.institution, uuid=uuidlib.uuid4(), value=v)
            self.lot.add(v)

    def _set_projection(self, root, **fields):
        ProductCache.objects.update_or_create(
            owner=self.institution, root=root, defaults=fields)

    def _row_ids(self, **params):
        req = RequestFactory().get("/", params)
        req.user = self.user
        view = LotDashboardView()
        view.request = req
        view.kwargs = {"pk": self.lot.pk}
        view.object = self.lot
        return [r['id'] for r in view.get_table_data()]

    def test_sort_by_manufacturer_asc_and_desc(self):
        self._set_projection("ereuse24:aaaaaa", manufacturer="Zeta")
        self._set_projection("ereuse24:bbbbbb", manufacturer="Alpha")
        self.assertEqual(
            self._row_ids(sort="manufacturer"),
            ["ereuse24:bbbbbb", "ereuse24:aaaaaa"])
        self.assertEqual(
            self._row_ids(sort="-manufacturer"),
            ["ereuse24:aaaaaa", "ereuse24:bbbbbb"])

    def test_sort_by_type(self):
        self._set_projection("ereuse24:aaaaaa", type="Server")
        self._set_projection("ereuse24:bbbbbb", type="Laptop")
        self.assertEqual(
            self._row_ids(sort="type"),
            ["ereuse24:bbbbbb", "ereuse24:aaaaaa"])

    def test_sort_by_model(self):
        self._set_projection("ereuse24:aaaaaa", model="M2")
        self._set_projection("ereuse24:bbbbbb", model="M1")
        self.assertEqual(
            self._row_ids(sort="model"),
            ["ereuse24:bbbbbb", "ereuse24:aaaaaa"])
