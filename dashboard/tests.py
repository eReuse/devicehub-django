import csv
import io
import json
import uuid as uuidlib
from unittest.mock import patch

from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.utils import timezone

from user.models import Institution, User
from evidence.models import SystemProperty, UserProperty, RootAlias
from device.product_cache import ProductCache
from action.models import State, StateDefinition
from lot.models import (
    Lot, LotTag, LotSubscription, Beneficiary, DeviceBeneficiary,
)
from dashboard.views import (
    LotDashboardView, AllDevicesView, UnassignedDevicesView, SearchView,
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


def _fake_xapian_search(ordered_uuids):
    """Build a stand-in for ``evidence.xapian.search``: an ``(institution,
    qs, offset, limit) -> matches`` callable backed by a fixed, relevance
    ordered list of uuids, so tests never touch a real Xapian database."""

    class _FakeDocument:
        def __init__(self, data):
            self._data = data

        def get_data(self):
            return self._data

    class _FakeMatch:
        def __init__(self, uuid):
            self.document = _FakeDocument(json.dumps({"uuid": str(uuid)}))

    class _FakeMSet(list):
        def size(self):
            return len(self)

    def fake_search(institution, qs, offset=0, limit=10):
        page = ordered_uuids[offset:offset + limit]
        return _FakeMSet(_FakeMatch(u) for u in page)

    return fake_search


class LotQueryParamTests(TestCase):
    """LotDashboardView reads the in-lot search filter from ``lquery`` (the
    old shared ``search`` param name is no longer read for the lot page)."""

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
        ProductCache.objects.update_or_create(
            owner=self.institution, root="ereuse24:aaaaaa",
            defaults={"manufacturer": "Samsung"})
        ProductCache.objects.update_or_create(
            owner=self.institution, root="ereuse24:bbbbbb",
            defaults={"manufacturer": "Dell"})

    def _view(self, lot=None, **params):
        lot = lot or self.lot
        req = RequestFactory().get("/", params)
        req.user = self.user
        view = LotDashboardView()
        view.request = req
        view.kwargs = {"pk": lot.pk}
        view.object = lot
        return view

    def test_lquery_filters_rows_within_the_lot(self):
        rows = self._view(lquery="samsung").get_table_data()
        self.assertEqual([r['id'] for r in rows], ["ereuse24:aaaaaa"])

        # The old shared param name is no longer read: it must not filter.
        rows = self._view(search="samsung").get_table_data()
        self.assertEqual(len(rows), 2)

    def test_lquery_search_is_scoped_to_the_current_lot(self):
        # A second lot with its own "Samsung" device, unrelated to self.lot.
        other_lot = Lot.objects.create(
            name="L2", owner=self.institution, type=self.tag)
        SystemProperty.objects.create(
            owner=self.institution, uuid=uuidlib.uuid4(),
            value="ereuse24:cccccc")
        other_lot.add("ereuse24:cccccc")
        ProductCache.objects.update_or_create(
            owner=self.institution, root="ereuse24:cccccc",
            defaults={"manufacturer": "Samsung"})

        row_ids = [r['id'] for r in
                   self._view(other_lot, lquery="samsung").get_table_data()]

        # Only the device that actually belongs to other_lot shows up...
        self.assertEqual(row_ids, ["ereuse24:cccccc"])
        # ...even though "ereuse24:aaaaaa" also matches "samsung" and is
        # visible in self.lot's own search (previous test).
        self.assertNotIn("ereuse24:aaaaaa", row_ids)


class SearchViewGqueryTests(TestCase):
    """SearchView reads the global search filter from ``gquery`` and merges
    the shortid (DB-only) and Xapian result lists preserving relevance order
    (shortid matches first, then Xapian matches in their ranked order)."""

    def setUp(self):
        self.institution = Institution.objects.create(name="Inst")
        self.user = User.objects.create(
            email="u@test.local", institution=self.institution)
        self.shortid_sp = SystemProperty.objects.create(
            owner=self.institution, uuid=uuidlib.uuid4(),
            value="ereuse24:acme12")
        self.top_sp = SystemProperty.objects.create(
            owner=self.institution, uuid=uuidlib.uuid4(),
            value="ereuse24:zzzxxx")
        self.second_sp = SystemProperty.objects.create(
            owner=self.institution, uuid=uuidlib.uuid4(),
            value="ereuse24:yyyxxx")

    def _view(self, **params):
        req = RequestFactory().get("/", params)
        req.user = self.user
        view = SearchView()
        view.request = req
        return view

    def test_gquery_merges_shortid_and_xapian_in_relevance_order(self):
        fake_search = _fake_xapian_search(
            [self.top_sp.uuid, self.second_sp.uuid])
        view = self._view(gquery="acme")
        with patch("dashboard.views.search", side_effect=fake_search):
            devices, total = view.get_devices(self.user, 0, 10)

        self.assertEqual(total, 3)
        self.assertEqual(
            [d.pk for d in devices],
            ["ereuse24:acme12", "ereuse24:zzzxxx", "ereuse24:yyyxxx"])

    def test_old_search_param_name_returns_nothing(self):
        view = self._view(search="acme")
        with patch("dashboard.views.search", side_effect=_fake_xapian_search([])):
            devices, total = view.get_devices(self.user, 0, 10)
        self.assertEqual((devices, total), ([], 0))


class SearchViewBestMatchTests(TestCase):
    """``?gquery=...&best_match=true`` redirects straight to the private
    device view of the top-relevance result, instead of rendering the
    results page. Any other value of ``best_match`` must not redirect."""

    def setUp(self):
        self.institution = Institution.objects.create(name="Inst")
        self.user = User.objects.create(
            email="u@test.local", institution=self.institution)
        self.top_sp = SystemProperty.objects.create(
            owner=self.institution, uuid=uuidlib.uuid4(),
            value="ereuse24:topone")
        self.second_sp = SystemProperty.objects.create(
            owner=self.institution, uuid=uuidlib.uuid4(),
            value="ereuse24:secondo")

    def _view(self, **params):
        req = RequestFactory().get("/", params)
        req.user = self.user
        view = SearchView()
        view.request = req
        view.kwargs = {}
        return view

    def test_best_match_true_redirects_following_relevance_order(self):
        # top_sp is ranked first by the (mocked) Xapian relevance order.
        fake_search = _fake_xapian_search([self.top_sp.uuid, self.second_sp.uuid])

        with patch("dashboard.views.search", side_effect=fake_search):
            view = self._view(gquery="unrelatedterm", best_match="true")
            response = view.get(view.request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("device:details", kwargs={"pk": "ereuse24:topone"}))

    def test_best_match_with_public_redirects_to_the_public_device_page(self):
        # top_sp is ranked first by the (mocked) Xapian relevance order.
        fake_search = _fake_xapian_search([self.top_sp.uuid, self.second_sp.uuid])

        with patch("dashboard.views.search", side_effect=fake_search):
            view = self._view(
                gquery="unrelatedterm", best_match="true", public="true")
            response = view.get(view.request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("device:device_web", kwargs={"pk": "ereuse24:topone"}))

    def test_best_match_not_true_does_not_redirect(self):
        # Stub out the normal results-page rendering: it builds real Device
        # objects (Xapian-backed), irrelevant to the redirect decision itself.
        fake_search = _fake_xapian_search([self.top_sp.uuid, self.second_sp.uuid])

        with patch("dashboard.views.search", side_effect=fake_search), \
                patch.object(SearchView, "get_context_data", return_value={}):
            view = self._view(gquery="unrelatedterm", best_match="false")
            response = view.get(view.request)
            self.assertNotEqual(response.status_code, 302)

            view = self._view(gquery="unrelatedterm")
            response = view.get(view.request)
            self.assertNotEqual(response.status_code, 302)


class SearchViewExactMatchTests(TestCase):
    """``?gquery=...&exact_match=true`` redirects only when the search
    yields exactly one result; any other match count falls back to the
    normal listing. When both ``best_match`` and ``exact_match`` are
    present, whichever appears last in the raw querystring wins."""

    def setUp(self):
        self.institution = Institution.objects.create(name="Inst")
        self.user = User.objects.create(
            email="u@test.local", institution=self.institution)
        self.top_sp = SystemProperty.objects.create(
            owner=self.institution, uuid=uuidlib.uuid4(),
            value="ereuse24:topone")
        self.second_sp = SystemProperty.objects.create(
            owner=self.institution, uuid=uuidlib.uuid4(),
            value="ereuse24:secondo")

    def _view(self, raw_query_string):
        req = RequestFactory().get("/?" + raw_query_string)
        req.user = self.user
        view = SearchView()
        view.request = req
        view.kwargs = {}
        return view

    def test_exact_match_true_redirects_when_there_is_a_single_result(self):
        fake_search = _fake_xapian_search([self.top_sp.uuid])

        with patch("dashboard.views.search", side_effect=fake_search):
            view = self._view("gquery=unrelatedterm&exact_match=true")
            response = view.get(view.request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("device:details", kwargs={"pk": "ereuse24:topone"}))

    def test_exact_match_with_public_redirects_to_the_public_device_page(self):
        fake_search = _fake_xapian_search([self.top_sp.uuid])

        with patch("dashboard.views.search", side_effect=fake_search):
            view = self._view(
                "gquery=unrelatedterm&exact_match=true&public=true")
            response = view.get(view.request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("device:device_web", kwargs={"pk": "ereuse24:topone"}))

    def test_exact_match_true_does_not_redirect_with_multiple_results(self):
        fake_search = _fake_xapian_search([self.top_sp.uuid, self.second_sp.uuid])

        with patch("dashboard.views.search", side_effect=fake_search), \
                patch.object(SearchView, "get_context_data", return_value={}):
            view = self._view("gquery=unrelatedterm&exact_match=true")
            response = view.get(view.request)

        self.assertNotEqual(response.status_code, 302)

    def test_exact_match_true_does_not_redirect_with_zero_results(self):
        fake_search = _fake_xapian_search([])

        with patch("dashboard.views.search", side_effect=fake_search), \
                patch.object(SearchView, "get_context_data", return_value={}):
            view = self._view("gquery=unrelatedterm&exact_match=true")
            response = view.get(view.request)

        self.assertNotEqual(response.status_code, 302)

    def test_last_param_in_url_wins_on_collision(self):
        # Two results: best_match alone would redirect (total >= 1), while
        # exact_match alone would not (total != 1). Whichever is last decides.
        fake_search = _fake_xapian_search([self.top_sp.uuid, self.second_sp.uuid])

        with patch("dashboard.views.search", side_effect=fake_search), \
                patch.object(SearchView, "get_context_data", return_value={}):
            # exact_match appears last -> wins -> no redirect (2 results).
            view = self._view(
                "gquery=unrelatedterm&best_match=true&exact_match=true")
            response = view.get(view.request)
            self.assertNotEqual(response.status_code, 302)

        with patch("dashboard.views.search", side_effect=fake_search):
            # best_match appears last -> wins -> redirects to top result.
            view = self._view(
                "gquery=unrelatedterm&exact_match=true&best_match=true")
            response = view.get(view.request)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(
                response.url,
                reverse("device:details", kwargs={"pk": "ereuse24:topone"}))

    def test_best_match_true_then_exact_match_false_disables_redirect(self):
        # exact_match=false is the last occurrence, so it wins over the
        # earlier best_match=true, and no redirect happens at all.
        fake_search = _fake_xapian_search([self.top_sp.uuid, self.second_sp.uuid])

        with patch("dashboard.views.search", side_effect=fake_search), \
                patch.object(SearchView, "get_context_data", return_value={}):
            view = self._view(
                "gquery=unrelatedterm&best_match=true&exact_match=false")
            response = view.get(view.request)

        self.assertNotEqual(response.status_code, 302)

    def test_exact_match_true_then_best_match_false_disables_redirect(self):
        # best_match=false is the last occurrence, so it wins over the
        # earlier exact_match=true, and no redirect happens at all, even
        # though there is exactly one result (which would satisfy exact_match).
        fake_search = _fake_xapian_search([self.top_sp.uuid])

        with patch("dashboard.views.search", side_effect=fake_search), \
                patch.object(SearchView, "get_context_data", return_value={}):
            view = self._view(
                "gquery=unrelatedterm&exact_match=true&best_match=false")
            response = view.get(view.request)

        self.assertNotEqual(response.status_code, 302)


class SearchViewCustomIdPublicRedirectTests(TestCase):
    """A device whose canonical root is a bare ``custom_id:...`` (a
    RootAlias-only root, with no SystemProperty of its own) must not be
    used verbatim as the pk for the public redirect: PublicDeviceWebView
    resolves devices by literal SystemProperty.value with no owner filter,
    so that pk would 404. The redirect must use the real physical alias
    (``web_pk``) instead. The private redirect is unaffected, since
    DetailsView resolves the canonical root fine using the owner."""

    def setUp(self):
        self.institution = Institution.objects.create(name="Inst")
        self.user = User.objects.create(
            email="u@test.local", institution=self.institution)
        self.real_alias = "ereuse24:realphys"
        SystemProperty.objects.create(
            owner=self.institution, uuid=uuidlib.uuid4(),
            key="ereuse24", value=self.real_alias)
        # SystemProperty creation auto-creates a self-referential RootAlias
        # row (alias == root == value); re-point it to the custom_id root.
        RootAlias.objects.update_or_create(
            owner=self.institution, alias=self.real_alias,
            defaults={"root": "custom_id:tstid1", "updated": timezone.now()})

    def _view(self, raw_query_string):
        req = RequestFactory().get("/?" + raw_query_string)
        req.user = self.user
        view = SearchView()
        view.request = req
        view.kwargs = {}
        return view

    def test_public_redirect_uses_web_pk_instead_of_the_bare_custom_id_root(self):
        with patch("dashboard.views.search", side_effect=_fake_xapian_search([])):
            view = self._view(
                "gquery=tstid1&exact_match=true&public=true")
            response = view.get(view.request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("device:device_web", kwargs={"pk": self.real_alias}))

    def test_private_redirect_keeps_the_canonical_custom_id_pk(self):
        with patch("dashboard.views.search", side_effect=_fake_xapian_search([])):
            view = self._view("gquery=tstid1&best_match=true")
            response = view.get(view.request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("device:details", kwargs={"pk": "custom_id:tstid1"}))
