import json
import os
import tempfile

from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from evidence.models import SystemProperty
from user.models import Institution, User


SNAPSHOT = {
    "type": "Snapshot",
    "uuid": "3a3b1a1e-6a3f-4a5b-8c9d-0e1f2a3b4c5d",
    "software": "Workbench",
    "version": "11.0",
    "endTime": "2026-01-01T00:00:00",
    "device": {
        "type": "Computer",
        "manufacturer": "Dell",
        "model": "Latitude",
        "serialNumber": "SN1",
    },
    "components": [],
}


class ReindexOnlyIndexTests(TestCase):
    """Restoring a lost xapian database must not touch the rows that are the
    real evidence."""

    def setUp(self):
        self.institution = Institution.objects.create(name="Inst")
        self.user = User.objects.create_user(
            email="admin@example.com",
            institution=self.institution,
            password="testpass123",
        )
        self.user.is_admin = True
        self.user.save()

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = os.path.join(self.tmp.name, self.institution.name)
        for sub in ["snapshots", "placeholders"]:
            os.makedirs(os.path.join(base, sub))
        with open(os.path.join(base, "snapshots", "s.json"), "w") as f:
            f.write(json.dumps(SNAPSHOT))

    def reindex(self, **options):
        with patch("evidence.parse.index") as index, \
                patch("evidence.management.commands.reindex.Command.EVIDENCES",
                      self.tmp.name):
            call_command("reindex", **options)
        return index

    def test_only_index_writes_the_document_but_no_properties(self):
        index = self.reindex(only_index=True)
        self.assertEqual(index.call_count, 1)
        self.assertFalse(SystemProperty.objects.exists())

    def test_without_the_flag_properties_are_created(self):
        index = self.reindex()
        self.assertEqual(index.call_count, 1)
        self.assertTrue(SystemProperty.objects.exists())

    def test_a_missing_subdirectory_is_logged_and_skipped(self):
        os.rmdir(os.path.join(
            self.tmp.name, self.institution.name, "placeholders"))

        with self.assertLogs("django", level="ERROR") as logs:
            index = self.reindex()

        self.assertIn("placeholders", "".join(logs.output))
        # the snapshots of the same institution are still indexed
        self.assertEqual(index.call_count, 1)
