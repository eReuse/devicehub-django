from action.models import DeviceLog
from evidence.models import UserProperty
from user.models import Institution

from api.tests.base import ApiTestCase


class DevicePropertyTest(ApiTestCase):

    def setUp(self):
        super().setUp()
        self.root = self.device_root("a" * 12)
        self.cache, self.prop = self.make_device(self.root)
        self.url = f"/api/v1/devices/{self.root}/properties/invoice/"

    def test_create_property_returns_201(self):
        response = self.client.post(
            self.url, {"value": "INV-1"},
            content_type="application/json", **self.auth)
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["action"], "created")
        self.assertEqual(body["property"]["value"], "INV-1")
        self.assertTrue(UserProperty.objects.filter(
            owner=self.institution, device_id=self.root, key="invoice").exists())

    def test_second_post_updates_instead_of_duplicating(self):
        self.client.post(self.url, {"value": "INV-1"},
                         content_type="application/json", **self.auth)
        response = self.client.post(self.url, {"value": "INV-2"},
                                    content_type="application/json", **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["action"], "updated")
        props = UserProperty.objects.filter(
            owner=self.institution, device_id=self.root, key="invoice")
        self.assertEqual(props.count(), 1)
        self.assertEqual(props.first().value, "INV-2")

    def test_create_property_writes_a_device_log(self):
        self.client.post(self.url, {"value": "INV-1"},
                         content_type="application/json", **self.auth)
        log = DeviceLog.objects.filter(institution=self.institution).first()
        self.assertIsNotNone(log)
        self.assertIn("invoice", log.event)

    def test_get_property_returns_the_stored_value(self):
        self.client.post(self.url, {"value": "INV-1"},
                         content_type="application/json", **self.auth)
        response = self.client.get(self.url, **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["property"]["value"], "INV-1")

    def test_get_missing_property_returns_404(self):
        response = self.client.get(self.url, **self.auth)
        self.assertEqual(response.status_code, 404)

    def test_delete_property_removes_it(self):
        self.client.post(self.url, {"value": "INV-1"},
                         content_type="application/json", **self.auth)
        response = self.client.delete(self.url, **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["action"], "deleted")
        self.assertFalse(UserProperty.objects.filter(
            owner=self.institution, device_id=self.root, key="invoice").exists())

    def test_delete_missing_property_returns_404(self):
        response = self.client.delete(self.url, **self.auth)
        self.assertEqual(response.status_code, 404)

    def test_unknown_device_returns_404(self):
        response = self.client.get(
            f"/api/v1/devices/{self.device_root('nope')}/properties/invoice/",
            **self.auth)
        self.assertEqual(response.status_code, 404)

    def test_empty_value_is_rejected(self):
        response = self.client.post(
            self.url, {"value": ""},
            content_type="application/json", **self.auth)
        self.assertEqual(response.status_code, 422)


class DeviceIsolationTest(ApiTestCase):
    """An institution must never reach another institution's devices."""

    def setUp(self):
        super().setUp()
        self.other_institution = Institution.objects.create(name="OtherOrg")
        self.other_user = self.make_user(self.other_institution, "other@test.com")
        self.other_root = self.device_root("b" * 12)
        self.make_device(self.other_root, institution=self.other_institution,
                         user=self.other_user)

    def test_foreign_device_property_returns_404(self):
        response = self.client.get(
            f"/api/v1/devices/{self.other_root}/properties/invoice/", **self.auth)
        self.assertEqual(response.status_code, 404)

    def test_foreign_device_is_absent_from_the_listing(self):
        own_root = self.device_root("c" * 12)
        self.make_device(own_root)
        response = self.client.get("/api/v1/devices/", **self.auth)
        ids = [d["ID"] for d in response.json()["devices"]]
        self.assertEqual(ids, [own_root])

    def test_foreign_device_cannot_be_written_by_bulk(self):
        response = self.client.post(
            "/api/v1/devices/bulk-properties/",
            {"device_ids": [self.other_root], "key": "k", "value": "v"},
            content_type="application/json", **self.auth)
        self.assertEqual(response.status_code, 422)
        self.assertFalse(UserProperty.objects.filter(device_id=self.other_root).exists())


class DeviceListTest(ApiTestCase):

    def setUp(self):
        super().setUp()
        self.roots = [self.device_root(f"{i:012d}") for i in range(3)]
        for root in self.roots:
            self.make_device(root)

    def test_listing_returns_every_device_with_pagination(self):
        response = self.client.get("/api/v1/devices/", **self.auth)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["pagination"]["total_items"], 3)
        self.assertEqual(body["pagination"]["current_page"], 1)
        self.assertEqual(len(body["devices"]), 3)

    def test_page_size_splits_the_result(self):
        response = self.client.get("/api/v1/devices/?size=2", **self.auth)
        body = response.json()
        self.assertEqual(body["pagination"]["total_pages"], 2)
        self.assertEqual(len(body["devices"]), 2)

    def test_page_beyond_the_last_one_returns_no_devices(self):
        response = self.client.get("/api/v1/devices/?page=99", **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["devices"], [])

    def test_filter_by_property_narrows_the_result(self):
        UserProperty.objects.create(
            owner=self.institution, user=self.user, device_id=self.roots[0],
            key="state", value="sold", type=UserProperty.Type.USER)
        response = self.client.get(
            "/api/v1/devices/?prop_key=state&prop_value=sold", **self.auth)
        body = response.json()
        self.assertEqual(body["pagination"]["total_items"], 1)
        self.assertEqual(body["devices"][0]["ID"], self.roots[0])

    def test_device_payload_exposes_user_properties(self):
        UserProperty.objects.create(
            owner=self.institution, user=self.user, device_id=self.roots[0],
            key="state", value="sold", type=UserProperty.Type.USER)
        response = self.client.get(
            "/api/v1/devices/?prop_key=state", **self.auth)
        self.assertEqual(
            response.json()["devices"][0]["user_properties"], {"state": "sold"})

    def test_only_undeclared_empty_cache_fields_are_left_out(self):
        """Dropping empty values only removes keys the schema does not declare:
        DeviceResponse fields are optional, so they come back as null."""
        root = self.device_root("d" * 12)
        self.make_device(root, data={
            "ram_type": "DDR4", "gpu_model": "", "custom_extra": ""})
        response = self.client.get("/api/v1/devices/", **self.auth)
        device = next(d for d in response.json()["devices"] if d["ID"] == root)
        self.assertEqual(device["ram_type"], "DDR4")
        self.assertIsNone(device["gpu_model"])
        self.assertNotIn("custom_extra", device)

    def test_device_payload_reports_when_it_was_first_seen(self):
        response = self.client.get("/api/v1/devices/", **self.auth)
        self.assertIsNotNone(response.json()["devices"][0]["created"])


class DevicePropertyKeysTest(ApiTestCase):

    def setUp(self):
        super().setUp()
        self.root = self.device_root("e" * 12)
        self.make_device(self.root)
        for key, value in [("invoice", "INV-1"), ("state", "sold")]:
            UserProperty.objects.create(
                owner=self.institution, user=self.user, device_id=self.root,
                key=key, value=value, type=UserProperty.Type.USER)

    def test_keys_endpoint_lists_the_keys_in_use(self):
        response = self.client.get("/api/v1/devices/properties/keys/", **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), ["invoice", "state"])

    def test_values_endpoint_lists_the_values_of_a_key(self):
        response = self.client.get(
            "/api/v1/devices/properties/invoice/values/", **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), ["INV-1"])


class DeviceLogsTest(ApiTestCase):

    def setUp(self):
        super().setUp()
        self.root = self.device_root("f" * 12)
        self.cache, self.prop = self.make_device(self.root)

    def test_logs_endpoint_returns_device_and_its_events(self):
        DeviceLog.objects.create(
            institution=self.institution, user=self.user,
            event="<Created> UserProperty: invoice: INV-1",
            snapshot_uuid=self.prop.uuid)
        response = self.client.get(
            f"/api/v1/devices/{self.root}/logs/", **self.auth)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["device"]["ID"], self.root)
        self.assertEqual(len(body["logs"]), 1)
        self.assertEqual(body["logs"][0]["user"], self.user.username)

    def test_logs_of_an_unknown_device_return_404(self):
        response = self.client.get(
            f"/api/v1/devices/{self.device_root('nope')}/logs/", **self.auth)
        self.assertEqual(response.status_code, 404)


class BulkPropertyTest(ApiTestCase):

    def setUp(self):
        super().setUp()
        self.roots = [self.device_root("1" * 12), self.device_root("2" * 12)]
        for root in self.roots:
            self.make_device(root)
        self.url = "/api/v1/devices/bulk-properties/"

    def test_all_valid_ids_return_200(self):
        response = self.client.post(
            self.url, {"device_ids": self.roots, "key": "state", "value": "sold"},
            content_type="application/json", **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            UserProperty.objects.filter(key="state", value="sold").count(), 2)

    def test_partial_success_returns_207(self):
        response = self.client.post(
            self.url,
            {"device_ids": self.roots + ["INVALID"], "key": "state", "value": "sold"},
            content_type="application/json", **self.auth)
        self.assertEqual(response.status_code, 207)
        self.assertEqual(response.json()["invalid_ids"], ["INVALID"])

    def test_no_valid_id_returns_422(self):
        response = self.client.post(
            self.url, {"device_ids": ["INVALID"], "key": "state", "value": "sold"},
            content_type="application/json", **self.auth)
        self.assertEqual(response.status_code, 422)

    def test_existing_property_is_updated_not_duplicated(self):
        self.client.post(
            self.url, {"device_ids": self.roots, "key": "state", "value": "sold"},
            content_type="application/json", **self.auth)
        self.client.post(
            self.url, {"device_ids": self.roots, "key": "state", "value": "kept"},
            content_type="application/json", **self.auth)
        props = UserProperty.objects.filter(key="state")
        self.assertEqual(props.count(), 2)
        self.assertEqual({p.value for p in props}, {"kept"})
