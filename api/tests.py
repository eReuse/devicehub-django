import uuid

from django.test import TestCase

from api.models import Token
from evidence.parse import Build
from evidence.tests.test_mobile_snapshot import mobile_snapshot
from user.models import Institution, User


class DeviceLookupApiTests(TestCase):
    """workbench-android checks the label id against this endpoint before sending."""

    def setUp(self):
        self.institution = Institution.objects.create(name="Test", country="ES")
        self.user = User.objects.create_user("u@example.org", self.institution, "1234")
        self.token = Token.objects.create(tag="test", token=uuid.uuid4(), owner=self.user)
        Build(mobile_snapshot("000123"), self.user)

    def get_logs(self, device_id):
        return self.client.get(
            f"/api/v1/devices/{device_id}/logs/",
            HTTP_AUTHORIZATION=f"Bearer {self.token.token}",
        )

    def test_existing_custom_id_returns_the_device(self):
        resp = self.get_logs("custom_id:000123")

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["device"]["ID"], "custom_id:000123")

    def test_unknown_custom_id_is_404(self):
        resp = self.get_logs("custom_id:000132")

        self.assertEqual(resp.status_code, 404)
