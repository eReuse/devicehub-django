from lot.models import DeviceLot
from user.models import Institution

from api.tests.base import ApiTestCase


class LotDevicesTest(ApiTestCase):

    def setUp(self):
        super().setUp()
        self.lot = self.make_lot(name="donante-orgA")
        self.root = self.device_root("a" * 12)
        self.make_device(self.root)
        DeviceLot.objects.create(lot=self.lot, device_id=self.root)
        self.url = f"/api/v1/lots/{self.lot.pk}/devices/"

    def test_lot_devices_are_listed_by_id(self):
        response = self.client.get(self.url, **self.auth)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["lot"]["name"], "donante-orgA")
        self.assertEqual([d["ID"] for d in body["devices"]], [self.root])

    def test_lot_can_be_addressed_by_name(self):
        response = self.client.get(
            "/api/v1/lots/donante-orgA/devices/", **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["lot"]["id"], self.lot.pk)

    def test_unknown_lot_returns_404(self):
        response = self.client.get("/api/v1/lots/9999/devices/", **self.auth)
        self.assertEqual(response.status_code, 404)

    def test_lot_of_another_institution_returns_404(self):
        other = Institution.objects.create(name="OtherOrg")
        foreign_lot = self.make_lot(name="foreign", institution=other)
        response = self.client.get(
            f"/api/v1/lots/{foreign_lot.pk}/devices/", **self.auth)
        self.assertEqual(response.status_code, 404)

    def test_empty_lot_returns_no_devices(self):
        empty_lot = self.make_lot(name="empty")
        response = self.client.get(
            f"/api/v1/lots/{empty_lot.pk}/devices/", **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["devices"], [])
        self.assertEqual(response.json()["pagination"]["total_items"], 0)


class LotAssignmentTest(ApiTestCase):

    def setUp(self):
        super().setUp()
        self.lot = self.make_lot()
        self.roots = [self.device_root("1" * 12), self.device_root("2" * 12)]
        for root in self.roots:
            self.make_device(root)
        self.url = f"/api/v1/lots/{self.lot.pk}/devices/"

    def test_assigning_valid_devices_returns_200(self):
        response = self.client.post(
            self.url, {"device_ids": self.roots},
            content_type="application/json", **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.lot.devicelot_set.count(), 2)

    def test_assigning_twice_does_not_duplicate(self):
        for _ in range(2):
            self.client.post(self.url, {"device_ids": self.roots},
                             content_type="application/json", **self.auth)
        self.assertEqual(self.lot.devicelot_set.count(), 2)

    def test_partial_assignment_returns_207(self):
        response = self.client.post(
            self.url, {"device_ids": self.roots + ["INVALID"]},
            content_type="application/json", **self.auth)
        self.assertEqual(response.status_code, 207)
        self.assertEqual(response.json()["invalid_ids"], ["INVALID"])

    def test_no_valid_device_returns_422(self):
        response = self.client.post(
            self.url, {"device_ids": ["INVALID"]},
            content_type="application/json", **self.auth)
        self.assertEqual(response.status_code, 422)

    def test_empty_device_list_is_rejected(self):
        response = self.client.post(
            self.url, {"device_ids": []},
            content_type="application/json", **self.auth)
        self.assertEqual(response.status_code, 422)

    def test_archived_lot_rejects_assignment_as_a_conflict(self):
        """Not 401: the token is valid, it is the lot state that forbids it."""
        archived = self.make_lot(name="archived-lot", archived=True)
        response = self.client.post(
            f"/api/v1/lots/{archived.pk}/devices/", {"device_ids": self.roots},
            content_type="application/json", **self.auth)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(archived.devicelot_set.count(), 0)

    def test_assigning_to_unknown_lot_returns_404(self):
        response = self.client.post(
            "/api/v1/lots/9999/devices/", {"device_ids": self.roots},
            content_type="application/json", **self.auth)
        self.assertEqual(response.status_code, 404)


class LotRemovalTest(ApiTestCase):

    def setUp(self):
        super().setUp()
        self.lot = self.make_lot()
        self.roots = [self.device_root("1" * 12), self.device_root("2" * 12)]
        for root in self.roots:
            self.make_device(root)
            DeviceLot.objects.create(lot=self.lot, device_id=root)
        self.url = f"/api/v1/lots/{self.lot.pk}/devices/"

    def test_removing_devices_empties_the_lot(self):
        response = self.client.delete(
            self.url, {"device_ids": self.roots},
            content_type="application/json", **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.lot.devicelot_set.count(), 0)

    def test_removing_one_device_keeps_the_others(self):
        self.client.delete(
            self.url, {"device_ids": [self.roots[0]]},
            content_type="application/json", **self.auth)
        self.assertEqual(
            list(self.lot.devicelot_set.values_list("device_id", flat=True)),
            [self.roots[1]])

    def test_removing_a_device_not_in_the_lot_is_not_an_error(self):
        other_root = self.device_root("3" * 12)
        self.make_device(other_root)
        response = self.client.delete(
            self.url, {"device_ids": [other_root]},
            content_type="application/json", **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.lot.devicelot_set.count(), 2)

    def test_archived_lot_rejects_removal_as_a_conflict(self):
        """An archived lot is frozen: devices cannot be taken out of it either."""
        self.lot.archived = True
        self.lot.save()
        response = self.client.delete(
            self.url, {"device_ids": self.roots},
            content_type="application/json", **self.auth)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.lot.devicelot_set.count(), 2)

    def test_removing_from_unknown_lot_returns_404(self):
        response = self.client.delete(
            "/api/v1/lots/9999/devices/", {"device_ids": self.roots},
            content_type="application/json", **self.auth)
        self.assertEqual(response.status_code, 404)
