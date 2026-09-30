import json
import uuid
from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings

from api.models import Token
from action.models import DeviceLog, Note, State, StateDefinition
from evidence.models import SystemProperty
from evidence.parse import Build
from user.models import Institution, User


def add_evidence(user):
    """Ingest the example Workbench snapshot as a new evidence."""
    path = Path(settings.BASE_DIR) / "example/snapshots/snapshot_workbench-script.json"
    snapshot = json.loads(path.read_text())
    snapshot["uuid"] = str(uuid.uuid4())
    Build(snapshot, user)
    return snapshot["uuid"]


class DeviceStateApiTests(TestCase):

    def setUp(self):
        self.institution = Institution.objects.create(name="Test", country="ES")
        self.user = User.objects.create_user("u@example.org", self.institution, "1234")
        self.token = Token.objects.create(tag="test", token=uuid.uuid4(), owner=self.user)
        self.evidence_uuid = add_evidence(self.user)
        self.url = f"/api/v1/devices/{SystemProperty.objects.get(uuid=self.evidence_uuid).value}"
        for order, state in enumerate(["INSTALL", "TEST"]):
            StateDefinition.objects.create(institution=self.institution, state=state, order=order)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.token.token}"}

    def post_state(self, state, expected, comment=None):
        payload = {"state": state, "expected_previous_state": expected, "comment": comment}
        return self.client.post(f"{self.url}/state/", payload, content_type="application/json", **self.auth)

    def test_get_state(self):
        resp = self.client.get(f"{self.url}/state/", **self.auth)

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIsNone(resp.json()["current_state"])
        self.assertEqual(resp.json()["available_states"], ["INSTALL", "TEST"])

    def test_post_creates_state_note_and_logs(self):
        resp = self.post_state("INSTALL", None, "Ready for installation")

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(resp.json()["changed"])
        self.assertEqual(State.objects.get().state, "INSTALL")
        self.assertEqual(Note.objects.get().description, "Ready for installation")
        self.assertEqual(DeviceLog.objects.count(), 2)

    def test_post_is_idempotent_and_rejects_stale_state(self):
        self.assertEqual(self.post_state("INSTALL", None).status_code, 200)

        retry = self.post_state("INSTALL", None)
        self.assertEqual(retry.status_code, 200)
        self.assertFalse(retry.json()["changed"])

        self.assertEqual(self.post_state("TEST", None).status_code, 409)

        resp = self.post_state("TEST", "INSTALL")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["previous_state"], "INSTALL")
        self.assertEqual(State.objects.count(), 2)

    def test_logs_use_state_from_older_evidence(self):
        State.objects.create(
            institution=self.institution, user=self.user,
            state="INSTALL", snapshot_uuid=self.evidence_uuid,
        )
        add_evidence(self.user)

        resp = self.client.get(f"{self.url}/logs/", **self.auth)

        self.assertEqual(resp.json()["device"]["current_state"], "INSTALL")

    def test_malformed_token_is_unauthorized(self):
        resp = self.client.get(f"{self.url}/state/", HTTP_AUTHORIZATION="Bearer not-a-uuid")

        self.assertEqual(resp.status_code, 401)

    @override_settings(CORS_ALLOWED_ORIGINS=["https://guide.example.org"])
    def test_cors_preflight_for_configured_origin(self):
        resp = self.client.options(
            f"{self.url}/state/",
            HTTP_ORIGIN="https://guide.example.org",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        )

        self.assertEqual(resp.headers["Access-Control-Allow-Origin"], "https://guide.example.org")
