import uuid as uuidlib
from unittest.mock import patch

from django.http import Http404
from django.test import RequestFactory, TestCase

from dashboard.views import AllDevicesView, SearchView, UnassignedDevicesView
from evidence.models import RootAlias, SystemProperty
from user.contributor import can_see, check_can_see, visible_roots
from user.models import Institution, User


class ContributorRoleTests(TestCase):
    """A contributor only sees the products with an evidence of its own
    (ereuse/projectes#965)."""

    def setUp(self):
        self.inst = Institution.objects.create(name="Inst")
        self.admin = User.objects.create(
            email="admin@test.local", institution=self.inst, is_admin=True)
        self.g1 = User.objects.create(
            email="g1@test.local", institution=self.inst, is_contributor=True)
        self.g2 = User.objects.create(
            email="g2@test.local", institution=self.inst, is_contributor=True)
        self.normal = User.objects.create(
            email="n@test.local", institution=self.inst)
        self.sp1 = self._sp(self.g1, "ereuse24:aaaaaa")
        self.sp2 = self._sp(self.g2, "ereuse24:bbbbbb")
        # g1's phone gets a custom id: still g1's.
        RootAlias.objects.filter(owner=self.inst, alias="ereuse24:aaaaaa") \
            .update(root="custom_id:G1PHONE")

    def _sp(self, user, value):
        return SystemProperty.objects.create(
            owner=self.inst, user=user, uuid=uuidlib.uuid4(), value=value)

    def _view(self, cls, user, **params):
        req = RequestFactory().get("/", params)
        req.user = user
        view = cls()
        view.request = req
        view.kwargs = {}
        return view

    def test_unrestricted_users(self):
        self.assertIsNone(visible_roots(self.admin))
        self.assertIsNone(visible_roots(self.normal))
        self.assertTrue(can_see(self.normal, "ereuse24:bbbbbb"))

    def test_all_products_only_lists_own(self):
        ids, count = self._view(AllDevicesView, self.g1).get_device_ids(0, 10)
        self.assertEqual((ids, count), (["custom_id:G1PHONE"], 1))
        ids, count = self._view(AllDevicesView, self.g2).get_device_ids(0, 10)
        self.assertEqual((ids, count), (["ereuse24:bbbbbb"], 1))
        _, count = self._view(AllDevicesView, self.normal).get_device_ids(0, 10)
        self.assertEqual(count, 2)

    def test_inbox_only_lists_own(self):
        ids, count = self._view(UnassignedDevicesView, self.g2).get_device_ids(0, 10)
        self.assertEqual((ids, count), (["ereuse24:bbbbbb"], 1))

    def test_detail_of_someone_elses_product_is_404(self):
        check_can_see(self.g1, "custom_id:G1PHONE")
        check_can_see(self.g1, "ereuse24:aaaaaa")
        with self.assertRaises(Http404):
            check_can_see(self.g1, "ereuse24:bbbbbb")

    def test_detail_view_returns_404(self):
        self.client.force_login(self.g1)
        r = self.client.get("/product/ereuse24:bbbbbb/")
        self.assertEqual(r.status_code, 404)

    def test_search_only_returns_own(self):
        def fake_search(institution, query, offset, limit):
            return None
        with patch("dashboard.views.search", side_effect=fake_search):
            devices, total = self._view(
                SearchView, self.g1, gquery="aaaaaa").get_devices(self.g1, 0, 10)
            self.assertEqual([d.id for d in devices], ["custom_id:G1PHONE"])
            devices, total = self._view(
                SearchView, self.g2, gquery="aaaaaa").get_devices(self.g2, 0, 10)
            self.assertEqual((devices, total), ([], 0))

    def test_new_product_becomes_visible(self):
        self._sp(self.g2, "ereuse24:cccccc")
        _, count = self._view(AllDevicesView, self.g2).get_device_ids(0, 10)
        self.assertEqual(count, 2)
