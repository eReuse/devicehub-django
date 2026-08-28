"""Requesting an evidence UUID that has no SystemProperty must return 404.

Before the fix, Evidence.__init__ called get_time() -> get_doc() -> search(None, ...),
which crashed in Xapian instead of letting the view answer 404.
"""
import uuid

from django.test import TestCase
from django.urls import reverse

from evidence.models import Evidence, SystemProperty
from user.models import Institution, User


class MissingEvidenceModelTests(TestCase):

    def test_evidence_with_unknown_uuid_does_not_raise(self):
        evidence = Evidence(str(uuid.uuid4()))

        self.assertEqual(list(evidence.properties), [])
        self.assertIsNone(evidence.owner)
        self.assertIsNone(evidence.created)


class MissingEvidenceViewTests(TestCase):

    def setUp(self):
        self.institution = Institution.objects.create(name="Inst A")
        self.user = User.objects.create_user(
            email="user@example.org",
            institution=self.institution,
            password="secret",
        )
        self.client.force_login(self.user)
        self.missing = uuid.uuid4()

    def test_details_returns_404(self):
        response = self.client.get(reverse("evidence:details", args=[self.missing]))
        self.assertEqual(response.status_code, 404)

    def test_download_returns_404(self):
        response = self.client.get(reverse("evidence:download", args=[self.missing]))
        self.assertEqual(response.status_code, 404)

    def test_photo_file_returns_404(self):
        response = self.client.get(reverse("evidence:photo_file", args=[self.missing]))
        self.assertEqual(response.status_code, 404)

    def test_erase_server_returns_404(self):
        response = self.client.get(reverse("evidence:erase_server", args=[self.missing]))
        self.assertEqual(response.status_code, 404)

    def test_evidence_from_another_institution_returns_403(self):
        other = Institution.objects.create(name="Inst B")
        foreign_uuid = uuid.uuid4()
        SystemProperty.objects.create(
            owner=other,
            uuid=foreign_uuid,
            value="ereuse24:ABC",
        )

        response = self.client.get(reverse("evidence:details", args=[foreign_uuid]))
        self.assertEqual(response.status_code, 403)
