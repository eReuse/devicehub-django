import hashlib
import os
import tempfile
from types import SimpleNamespace

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from django.utils.datastructures import MultiValueDict

from evidence.forms import PhotoForm
from evidence.image_processing import Build, photo_bundle_hash


def photo(content=b"photo-1", name="photo.jpg", content_type="image/jpeg"):
    return SimpleUploadedFile(name, content, content_type=content_type)


class PhotoFormTests(SimpleTestCase):
    def setUp(self):
        self.evidences_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.evidences_dir.cleanup)
        settings_override = override_settings(EVIDENCES_DIR=self.evidences_dir.name)
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        self.user = SimpleNamespace(institution=SimpleNamespace(name="org"))

    def form(self, photos):
        return PhotoForm(
            data={},
            files=MultiValueDict({"photo_file": photos}),
            user=self.user,
        )

    def test_accepts_several_photos_in_one_evidence(self):
        form = self.form([photo(b"front"), photo(b"back", name="back.png", content_type="image/png")])

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(len(form.photo_data_cache), 2)
        self.assertEqual(
            [data["hash"] for data in form.photo_data_cache],
            [hashlib.sha256(b"front").hexdigest(), hashlib.sha256(b"back").hexdigest()],
        )

    def test_requires_at_least_one_photo(self):
        form = self.form([])

        self.assertFalse(form.is_valid())
        self.assertIn("Select at least one photo.", form.errors["photo_file"])

    def test_rejects_more_than_ten_photos(self):
        form = self.form([photo(f"photo-{i}".encode()) for i in range(11)])

        self.assertFalse(form.is_valid())
        self.assertIn("You can attach at most 10 photos.", form.errors["photo_file"])

    def test_accepts_exactly_ten_photos(self):
        form = self.form([photo(f"photo-{i}".encode()) for i in range(10)])

        self.assertTrue(form.is_valid(), form.errors)

    def test_rejects_the_same_photo_twice(self):
        form = self.form([photo(b"same"), photo(b"same", name="copy.jpg")])

        self.assertFalse(form.is_valid())
        self.assertIn(
            "The same photo was selected more than once.", form.errors["photo_file"]
        )

    def test_rejects_photos_over_ten_megabytes(self):
        form = self.form([photo(b"x" * (10 * 1024 * 1024 + 1))])

        self.assertFalse(form.is_valid())
        self.assertIn("File size exceeds 10MB limit", form.errors["photo_file"])

    def test_rejects_non_image_content_type(self):
        form = self.form([photo(content_type="application/pdf")])

        self.assertFalse(form.is_valid())
        self.assertIn("Invalid file type.", form.errors["photo_file"])

    def test_rejects_non_image_extension(self):
        form = self.form([photo(name="photo.pdf")])

        self.assertFalse(form.is_valid())
        self.assertIn("Invalid file extension.", form.errors["photo_file"])

    def test_rejects_a_photo_already_stored_for_the_institution(self):
        sha256 = hashlib.sha256(b"stored").hexdigest()
        photos_dir = os.path.join(self.evidences_dir.name, "org", "photos")
        os.makedirs(photos_dir)
        open(os.path.join(photos_dir, f"{sha256}.jpg"), "wb").close()

        form = self.form([photo(b"stored")])

        self.assertFalse(form.is_valid())
        self.assertIn("Photo already exists.", form.errors["photo_file"])


class PhotoEvidenceIdentityTests(SimpleTestCase):
    def details_hash(self, json):
        build = SimpleNamespace(json=json)
        Build.get_details(build)
        return build.hash

    def test_single_photo_evidence_keeps_its_photo_hash(self):
        self.assertEqual(self.details_hash({"photo": {"hash": "abc"}}), "abc")

    def test_bundle_with_one_photo_uses_that_photo_hash(self):
        self.assertEqual(photo_bundle_hash([{"hash": "abc"}]), "abc")

    def test_bundle_hash_ignores_photo_order(self):
        self.assertEqual(
            photo_bundle_hash([{"hash": "a"}, {"hash": "b"}]),
            photo_bundle_hash([{"hash": "b"}, {"hash": "a"}]),
        )

    def test_multi_photo_evidence_is_identified_by_the_bundle(self):
        photos = [{"hash": "a"}, {"hash": "b"}]

        self.assertEqual(
            self.details_hash({"photos": photos}), photo_bundle_hash(photos)
        )

    def test_stored_bundle_hash_takes_precedence(self):
        self.assertEqual(
            self.details_hash({"photo_hash": "stored", "photos": [{"hash": "a"}]}),
            "stored",
        )
