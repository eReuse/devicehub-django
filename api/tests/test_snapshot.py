import os
import shutil
import tempfile
import uuid as uuidlib

from django.conf import settings
from django.test import override_settings

from device.models import ProductCache
from evidence.models import SystemProperty

from api.tests.base import ApiTestCase, load_base_snapshot

URL = "/api/v1/snapshot/"


class SnapshotValidationTest(ApiTestCase):
    """Rejections that happen before anything is written to disk."""

    def test_invalid_json_is_rejected(self):
        response = self.client.post(
            URL, "{not json", content_type="application/json", **self.auth)
        self.assertIn(response.status_code, (400, 422))

    def test_snapshot_without_uuid_returns_422(self):
        data = load_base_snapshot()
        del data["uuid"]
        response = self.client.post(
            URL, data, content_type="application/json", **self.auth)
        self.assertEqual(response.status_code, 422)

    def test_duplicate_uuid_returns_409(self):
        data = load_base_snapshot()
        SystemProperty.objects.create(
            owner=self.institution, user=self.user, uuid=data["uuid"],
            key=settings.DEVICEHUB_ALGORITHM_DEVICE,
            value=self.device_root("a" * 12))
        response = self.client.post(
            URL, data, content_type="application/json", **self.auth)
        self.assertEqual(response.status_code, 409)

    def test_duplicate_is_detected_before_touching_the_disk(self):
        """The duplicate check runs first, so a resend leaves no stray file."""
        data = load_base_snapshot()
        SystemProperty.objects.create(
            owner=self.institution, user=self.user, uuid=data["uuid"],
            key=settings.DEVICEHUB_ALGORITHM_DEVICE,
            value=self.device_root("a" * 12))
        evidences_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, evidences_dir, True)
        with override_settings(EVIDENCES_DIR=evidences_dir):
            self.client.post(URL, data, content_type="application/json", **self.auth)
        self.assertEqual(os.listdir(evidences_dir), [])

    def test_snapshot_requires_authentication(self):
        response = self.client.post(
            URL, load_base_snapshot(), content_type="application/json")
        self.assertEqual(response.status_code, 401)


class SnapshotUploadTest(ApiTestCase):
    """End-to-end upload of the reference workbench-script snapshot."""

    def setUp(self):
        super().setUp()
        self.evidences_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(
            self.evidences_dir, self.institution.name, "snapshots"))
        self.addCleanup(shutil.rmtree, self.evidences_dir, True)
        self.settings_override = override_settings(EVIDENCES_DIR=self.evidences_dir)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.data = load_base_snapshot()

    def post_snapshot(self, data=None):
        return self.client.post(
            URL, data if data is not None else self.data,
            content_type="application/json", **self.auth)

    def test_upload_returns_the_device_urls(self):
        response = self.post_snapshot()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "success")
        root = SystemProperty.objects.get(
            owner=self.institution, uuid=self.data["uuid"],
            key=settings.DEVICEHUB_ALGORITHM_DEVICE).value
        cache = ProductCache.objects.get(owner=self.institution, root=root)
        self.assertEqual(body["dhid"], cache.shortid)
        self.assertIn(root, body["url"])
        self.assertTrue(body["public_url"].endswith("/public/"))

    def test_upload_registers_the_evidence_for_the_institution(self):
        self.post_snapshot()
        prop = SystemProperty.objects.filter(
            owner=self.institution, uuid=self.data["uuid"],
            key=settings.DEVICEHUB_ALGORITHM_DEVICE).first()
        self.assertIsNotNone(prop)
        self.assertEqual(prop.user, self.user)

    def test_upload_builds_the_device_projection(self):
        self.post_snapshot()
        prop = SystemProperty.objects.get(
            owner=self.institution, uuid=self.data["uuid"],
            key=settings.DEVICEHUB_ALGORITHM_DEVICE)
        self.assertTrue(ProductCache.objects.filter(
            owner=self.institution, root=prop.value).exists())

    def test_uploaded_device_shows_up_in_the_listing(self):
        dhid = self.post_snapshot().json()["dhid"]
        response = self.client.get("/api/v1/devices/", **self.auth)
        shortids = [d["shortId"] for d in response.json()["devices"]]
        self.assertIn(dhid, shortids)

    def test_resending_the_same_snapshot_returns_409(self):
        self.post_snapshot()
        response = self.post_snapshot()
        self.assertEqual(response.status_code, 409)

    def test_same_snapshot_with_a_new_uuid_is_accepted(self):
        self.post_snapshot()
        second = load_base_snapshot()
        second["uuid"] = str(uuidlib.uuid4())
        response = self.post_snapshot(second)
        self.assertEqual(response.status_code, 200)

    def test_snapshot_file_is_kept_out_of_the_errors_folder(self):
        self.post_snapshot()
        errors_dir = os.path.join(
            self.evidences_dir, self.institution.name, "snapshots", "errors")
        self.assertEqual(os.listdir(errors_dir), [])
