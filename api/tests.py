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
    """Ingest the example Workbench snapshot as fresh evidence; return it."""
    with open(Path(settings.BASE_DIR) / "example/snapshots/snapshot_workbench-script.json") as f:
        snapshot = json.load(f)
    snapshot["uuid"] = str(uuid.uuid4())
    Build(snapshot, user)
    return snapshot


class DeviceStateApiTests(TestCase):

    def setUp(self):
        self.institution = Institution.objects.create(name="Test", country="ES")
        self.user = User.objects.create_user("u@example.org", self.institution, "1234")
        self.token = Token.objects.create(tag="test", token=uuid.uuid4(), owner=self.user)
        self.first_snapshot = add_evidence(self.user)
        self.device_id = SystemProperty.objects.get(
            uuid=self.first_snapshot["uuid"]
        ).value
        StateDefinition.objects.create(
            institution=self.institution, state="INSTALL", order=1
        )
        StateDefinition.objects.create(
            institution=self.institution, state="TEST", order=2
        )

    def get_logs(self, device_id):
        return self.client.get(
            f"/api/v1/devices/{device_id}/logs/",
            HTTP_AUTHORIZATION=f"Bearer {self.token.token}",
        )

    def state_request(self, method="get", payload=None):
        return getattr(self.client, method)(
            f"/api/v1/devices/{self.device_id}/state/",
            data=payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token.token}",
        )

    def test_unknown_device_is_404(self):
        resp = self.get_logs("custom_id:does-not-exist")

        self.assertEqual(resp.status_code, 404)

    def test_malformed_token_is_unauthorized(self):
        resp = self.client.get(
            f"/api/v1/devices/{self.device_id}/state/",
            HTTP_AUTHORIZATION="Bearer not-a-uuid",
        )

        self.assertEqual(resp.status_code, 401)

    @override_settings(CORS_ALLOWED_ORIGINS=["https://guide.example.org"])
    def test_state_api_allows_configured_browser_origin(self):
        resp = self.client.options(
            f"/api/v1/devices/{self.device_id}/state/",
            HTTP_ORIGIN="https://guide.example.org",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization, content-type",
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.headers["Access-Control-Allow-Origin"],
            "https://guide.example.org",
        )
        self.assertIn("authorization", resp.headers["Access-Control-Allow-Headers"])

    @override_settings(CORS_ALLOW_ALL_ORIGINS=True)
    def test_state_api_can_allow_any_origin(self):
        resp = self.client.options(
            f"/api/v1/devices/{self.device_id}/state/",
            HTTP_ORIGIN="http://localhost:8765",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers["Access-Control-Allow-Origin"], "*")
        self.assertNotIn("Access-Control-Allow-Credentials", resp.headers)

    def test_get_state_lists_available_states(self):
        resp = self.state_request()

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIsNone(resp.json()["current_state"])
        self.assertEqual(resp.json()["available_states"], ["INSTALL", "TEST"])

    def test_post_state_creates_state_note_and_logs(self):
        resp = self.state_request("post", {
            "state": "INSTALL",
            "expected_previous_state": None,
            "comment": "Ready for installation",
        })

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(resp.json()["changed"])
        self.assertEqual(resp.json()["current_state"], "INSTALL")
        self.assertEqual(State.objects.get().state, "INSTALL")
        self.assertEqual(Note.objects.get().description, "Ready for installation")
        self.assertEqual(DeviceLog.objects.count(), 2)

    def test_post_state_is_idempotent(self):
        payload = {"state": "INSTALL", "expected_previous_state": None}
        self.assertEqual(self.state_request("post", payload).status_code, 200)

        resp = self.state_request("post", payload)

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertFalse(resp.json()["changed"])
        self.assertEqual(State.objects.count(), 1)

    def test_post_state_advances_from_expected_state(self):
        self.assertEqual(self.state_request("post", {
            "state": "INSTALL", "expected_previous_state": None,
        }).status_code, 200)

        resp = self.state_request("post", {
            "state": "TEST", "expected_previous_state": "INSTALL",
        })

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["previous_state"], "INSTALL")
        self.assertEqual(resp.json()["current_state"], "TEST")
        self.assertEqual(State.objects.count(), 2)

    def test_post_state_rejects_stale_previous_state(self):
        State.objects.create(
            institution=self.institution,
            user=self.user,
            state="INSTALL",
            snapshot_uuid=self.first_snapshot["uuid"],
        )

        resp = self.state_request("post", {
            "state": "TEST",
            "expected_previous_state": None,
        })

        self.assertEqual(resp.status_code, 409, resp.content)
        self.assertEqual(State.objects.count(), 1)

    def test_logs_keep_state_from_older_evidence(self):
        State.objects.create(
            institution=self.institution,
            user=self.user,
            state="INSTALL",
            snapshot_uuid=self.first_snapshot["uuid"],
        )
        add_evidence(self.user)

        resp = self.get_logs(self.device_id)

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["device"]["current_state"], "INSTALL")
