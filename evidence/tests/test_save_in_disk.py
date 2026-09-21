"""
Regression tests for snapshot storage on disk.
"""
import os
import tempfile
import uuid

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from evidence.forms import UploadForm
from user.models import Institution, User
from utils.save_snapshots import save_in_disk


SNAPSHOTS = [
    "example/dpp-snapshots/hp_probook_450.json",
    "example/dpp-snapshots/hp_probook_g2.json",
]


class SaveInDiskTest(TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

    def test_institution_name_with_spaces(self):
        institution = Institution.objects.create(
            name="Cooperativa de trabajo Ltda"
        )
        data = {"uuid": str(uuid.uuid4())}

        with override_settings(EVIDENCES_DIR=self.tmpdir.name):
            path_name = save_in_disk(data, institution.name)

        self.assertTrue(os.path.isfile(path_name))


class RenameInstitutionTest(TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

        self.institution = Institution.objects.create(name="Pangea")
        self.user = User.objects.create_user(
            email="admin@test.com",
            institution=self.institution,
            password="pass1234",
        )

    def upload(self, path):
        with open(path, "rb") as f:
            upload = SimpleUploadedFile(os.path.basename(path), f.read())

        form = UploadForm(files={"evidence_file": [upload]})
        self.assertTrue(form.is_valid(), form.errors)
        form.save(self.user)

    def institution_dirs(self):
        dirs = set()
        for root, _subdirs, files in os.walk(self.tmpdir.name):
            for name in files:
                if name.endswith(".json"):
                    relative = os.path.relpath(root, self.tmpdir.name)
                    dirs.add(relative.split(os.sep)[0])
        return dirs

    def test_snapshots_stay_together_after_rename(self):
        with override_settings(EVIDENCES_DIR=self.tmpdir.name):
            self.upload(SNAPSHOTS[0])

            self.institution.name = "Reuse"
            self.institution.save(update_fields=["name"])

            self.upload(SNAPSHOTS[1])

        self.assertEqual(len(self.institution_dirs()), 1)
