import json
import os
import shutil
import tempfile

import xapian

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from device.models import DeviceType, DeviceTypeAttribute, ProductCache
from evidence.models import RootAlias, SystemProperty
from user.models import Institution

from api.tests.base import ApiTestCase

URL = "/api/v1/devices/"


def make_evidences_dir(test, institution):
    """An evidences dir is also the Xapian database every doc lookup goes through."""
    evidences_dir = tempfile.mkdtemp()
    for place in ["placeholders", "snapshots"]:
        os.makedirs(os.path.join(evidences_dir, institution.name, place))
    xapian.WritableDatabase(evidences_dir, xapian.DB_CREATE_OR_OPEN).close()
    test.addCleanup(shutil.rmtree, evidences_dir, True)
    return evidences_dir


def photo(name="product.jpg", content_type="image/jpeg"):
    return SimpleUploadedFile(name, os.urandom(64), content_type=content_type)


class ProductCreationTest(ApiTestCase):
    """Manual registration, the API counterpart of the /product/add/ form."""

    def setUp(self):
        super().setUp()
        self.evidences_dir = make_evidences_dir(self, self.institution)
        self.settings_override = override_settings(EVIDENCES_DIR=self.evidences_dir)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        DeviceType.objects.create(institution=self.institution, name="Laptop")

    def post(self, payload):
        payload = dict(payload)
        if "attributes" in payload:
            payload["attributes"] = json.dumps(payload["attributes"])
        return self.client.post(URL, payload, **self.auth)

    def test_registering_a_product_returns_201_and_its_urls(self):
        response = self.post({"type": "Laptop"})
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "success")
        self.assertEqual(len(body["products"]), 1)
        product = body["products"][0]
        self.assertIn(product["ID"], product["url"])
        self.assertTrue(product["public_url"].endswith("/public/"))

    def test_registered_product_becomes_an_evidence_and_a_projection(self):
        product_id = self.post({"type": "Laptop"}).json()["products"][0]["ID"]
        self.assertTrue(SystemProperty.objects.filter(
            owner=self.institution, key="web25", value=product_id).exists())
        self.assertTrue(ProductCache.objects.filter(
            owner=self.institution, root=product_id).exists())

    def test_attributes_are_stored_with_the_product(self):
        self.post({"type": "Laptop",
                   "attributes": {"manufacturer": "Dell", "model": "Latitude"}})
        response = self.client.get(URL, **self.auth)
        device = response.json()["devices"][0]
        self.assertEqual(device["manufacturer"], "Dell")
        self.assertEqual(device["model"], "Latitude")

    def test_amount_registers_that_many_products(self):
        response = self.post({"type": "Laptop", "amount": 3})
        self.assertEqual(len(response.json()["products"]), 3)
        self.assertEqual(SystemProperty.objects.filter(
            owner=self.institution, key="web25").count(), 3)

    def test_custom_id_becomes_the_canonical_identifier(self):
        product = self.post(
            {"type": "Laptop", "custom_id": "INV-001"}).json()["products"][0]
        self.assertEqual(product["ID"], "custom_id:inv-001")
        self.assertTrue(RootAlias.objects.filter(
            owner=self.institution, root="custom_id:inv-001").exists())

    def test_custom_id_registers_a_single_product(self):
        response = self.post(
            {"type": "Laptop", "amount": 5, "custom_id": "INV-001"})
        self.assertEqual(len(response.json()["products"]), 1)

    def test_custom_id_already_in_use_is_rejected(self):
        self.post({"type": "Laptop", "custom_id": "INV-001"})
        response = self.post({"type": "Laptop", "custom_id": "INV-001"})
        self.assertEqual(response.status_code, 422)
        self.assertIn("custom_id", response.json()["details"])

    def test_unknown_type_is_rejected(self):
        response = self.post({"type": "Spaceship"})
        self.assertEqual(response.status_code, 422)
        self.assertIn("type", response.json()["details"])

    def test_type_of_another_institution_is_rejected(self):
        DeviceType.objects.create(
            institution=Institution.objects.create(name="OtherOrg"), name="Server")
        response = self.post({"type": "Server"})
        self.assertEqual(response.status_code, 422)

    def test_missing_type_is_rejected(self):
        response = self.post({"attributes": {"model": "Latitude"}})
        self.assertEqual(response.status_code, 422)

    def test_registering_requires_authentication(self):
        response = self.client.post(URL, {"type": "Laptop"})
        self.assertEqual(response.status_code, 401)


class ProductPhotoTest(ApiTestCase):
    """The photo travels in the same request as the data, as it does in the web form."""

    def setUp(self):
        super().setUp()
        self.evidences_dir = make_evidences_dir(self, self.institution)
        self.settings_override = override_settings(EVIDENCES_DIR=self.evidences_dir)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        DeviceType.objects.create(institution=self.institution, name="Laptop")

    def post(self, payload):
        return self.client.post(URL, payload, **self.auth)

    def test_photo_is_stored_as_an_evidence_of_the_product(self):
        response = self.post({"type": "Laptop", "photo": photo()})
        self.assertEqual(response.status_code, 201)
        product_id = response.json()["products"][0]["ID"]
        photo_prop = SystemProperty.objects.get(
            owner=self.institution, key="photo25")
        self.assertTrue(RootAlias.objects.filter(
            owner=self.institution, root=product_id,
            alias=photo_prop.value).exists())

    def test_photo_file_lands_in_the_institution_photos_dir(self):
        self.post({"type": "Laptop", "photo": photo()})
        photos_dir = os.path.join(
            self.evidences_dir, self.institution.name, "photos")
        self.assertEqual(len(os.listdir(photos_dir)), 1)

    def test_photo_registers_a_single_product(self):
        response = self.post({"type": "Laptop", "amount": 4, "photo": photo()})
        self.assertEqual(len(response.json()["products"]), 1)

    def test_product_without_photo_has_no_photo_evidence(self):
        self.post({"type": "Laptop"})
        self.assertFalse(SystemProperty.objects.filter(key="photo25").exists())

    def test_photo_with_a_forbidden_type_is_rejected(self):
        response = self.post({
            "type": "Laptop",
            "photo": photo("product.txt", content_type="text/plain"),
        })
        self.assertEqual(response.status_code, 422)
        self.assertIn("photo", response.json()["details"])

    def test_the_same_photo_twice_is_rejected(self):
        image = photo()
        self.post({"type": "Laptop", "photo": image})
        image.seek(0)
        response = self.post({"type": "Laptop", "photo": image})
        self.assertEqual(response.status_code, 422)


class ExistingProductPhotoTest(ApiTestCase):
    """A photo uploaded on its own always lands on the canonical id of a product."""

    def setUp(self):
        super().setUp()
        self.evidences_dir = make_evidences_dir(self, self.institution)
        self.settings_override = override_settings(EVIDENCES_DIR=self.evidences_dir)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.root = self.device_root("abc123")
        self.cache, self.prop = self.make_device(self.root)

    def post(self, device_id, image=None, auth=True):
        credentials = self.auth if auth else {}
        return self.client.post(
            "{}{}/photo/".format(URL, device_id),
            {"photo": image or photo()}, **credentials)

    def linked_root(self):
        photo_prop = SystemProperty.objects.get(
            owner=self.institution, key="photo25")
        return RootAlias.objects.get(
            owner=self.institution, alias=photo_prop.value).root

    def test_photo_is_linked_to_the_product_it_names(self):
        response = self.post(self.root)
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["ID"], self.root)
        self.assertEqual(self.linked_root(), self.root)
        self.assertIn(body["uuid"], body["url"])

    def test_photo_named_by_an_alias_is_linked_to_its_root(self):
        RootAlias.set_alias(
            owner=self.institution, alias=self.root,
            new_root="custom_id:inv-9", user=self.user)
        response = self.post(self.root)
        self.assertEqual(response.json()["ID"], "custom_id:inv-9")
        self.assertEqual(self.linked_root(), "custom_id:inv-9")

    def test_photo_named_by_a_custom_id_is_linked_to_it(self):
        RootAlias.set_alias(
            owner=self.institution, alias=self.root,
            new_root="custom_id:inv-9", user=self.user)
        response = self.post("custom_id:inv-9")
        self.assertEqual(self.linked_root(), "custom_id:inv-9")
        self.assertEqual(response.status_code, 201)

    def test_photo_file_lands_in_the_institution_photos_dir(self):
        self.post(self.root)
        photos_dir = os.path.join(
            self.evidences_dir, self.institution.name, "photos")
        self.assertEqual(len(os.listdir(photos_dir)), 1)

    def test_unknown_product_is_rejected(self):
        response = self.post(self.device_root("nothinghere"))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(SystemProperty.objects.filter(key="photo25").exists())

    def test_product_of_another_institution_is_rejected(self):
        other = Institution.objects.create(name="OtherOrg")
        root = self.device_root("otherorg")
        self.make_device(root, institution=other,
                         user=self.make_user(other, "other@test.com"))
        self.assertEqual(self.post(root).status_code, 404)

    def test_photo_with_a_forbidden_type_is_rejected(self):
        response = self.post(
            self.root, photo("product.txt", content_type="text/plain"))
        self.assertEqual(response.status_code, 422)
        self.assertIn("photo", response.json()["details"])

    def test_the_same_photo_twice_is_rejected(self):
        image = photo()
        self.post(self.root, image)
        image.seek(0)
        self.assertEqual(self.post(self.root, image).status_code, 422)

    def test_a_second_photo_can_be_linked_to_the_same_product(self):
        self.post(self.root)
        self.assertEqual(self.post(self.root).status_code, 201)
        self.assertEqual(RootAlias.objects.filter(
            owner=self.institution, root=self.root).count(), 3)

    def test_photo_without_a_product_id_is_not_accepted(self):
        response = self.client.post(URL + "photo/", {"photo": photo()}, **self.auth)
        self.assertEqual(response.status_code, 404)

    def test_uploading_requires_authentication(self):
        self.assertEqual(self.post(self.root, auth=False).status_code, 401)


class ProductTypelistTest(ApiTestCase):

    def setUp(self):
        super().setUp()
        self.laptop = DeviceType.objects.create(
            institution=self.institution, name="Laptop", label="Portátil",
            icon="bi-laptop", order=1)
        DeviceType.objects.create(
            institution=self.institution, name="Monitor", order=2)
        for name in ["manufacturer", "model"]:
            DeviceTypeAttribute.objects.create(device_type=self.laptop, name=name)
        self.url = "/api/v1/devices/types/"

    def test_types_are_listed_with_their_attributes(self):
        response = self.client.get(self.url, **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [
            {"name": "Laptop", "display_name": "Portátil", "icon": "bi-laptop",
             "attributes": ["manufacturer", "model"]},
            {"name": "Monitor", "display_name": "Monitor", "icon": "",
             "attributes": []},
        ])

    def test_types_of_another_institution_are_absent(self):
        DeviceType.objects.create(
            institution=Institution.objects.create(name="OtherOrg"), name="Server")
        response = self.client.get(self.url, **self.auth)
        self.assertNotIn("Server", [t["name"] for t in response.json()])

    def test_listing_types_requires_authentication(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_listed_type_can_be_used_to_register_a_product(self):
        evidences_dir = make_evidences_dir(self, self.institution)
        name = self.client.get(self.url, **self.auth).json()[0]["name"]
        with override_settings(EVIDENCES_DIR=evidences_dir):
            response = self.client.post(URL, {"type": name}, **self.auth)
        self.assertEqual(response.status_code, 201)
