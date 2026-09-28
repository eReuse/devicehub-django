from datetime import datetime
from unittest.mock import MagicMock, patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, SimpleTestCase, TestCase

from device.views import DetailsView
from environmental_impact.algorithms.ereuse2026.ereuse2026 import load_factors, load_grid
from environmental_impact.algorithms.ereuse2026.model import DeviceInputs, EvidencePoint, compute_device
from environmental_impact.presenters import device_impact_view
from environmental_impact.reuse import REUSE_START_KEY
from evidence.models import UserProperty
from user.models import Institution, User

E0 = "5f0c3b0e-0000-4000-8000-000000000000"
E1 = "5f0c3b0e-0000-4000-8000-000000000001"


class SaveReuseStartTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name="Test Institution", country="ES")
        self.user = User.objects.create_user(
            email="test@example.com", institution=self.institution, password="testpass123"
        )
        self.device_id = "ereuse24:test-device"

    def _post(self, value):
        request = RequestFactory().post(
            f"/product/{self.device_id}/", {"action": "save_reuse_start", "reuse_start": value}
        )
        request.user = self.user
        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        setattr(request, "_messages", FallbackStorage(request))
        device = MagicMock()
        device.uuids = [E0, E1]
        with patch("device.views.Device", return_value=device):
            return DetailsView()._save_reuse_start(request, self.device_id)

    def _marks(self):
        return list(
            UserProperty.objects.filter(owner=self.institution, key=REUSE_START_KEY).values_list("uuid", flat=True)
        )

    def test_marks_the_selected_evidence(self):
        response = self._post(E1)
        self.assertEqual([str(u) for u in self._marks()], [E1])
        self.assertEqual(response.url, f"/product/{self.device_id}/#environmental_impact")

    def test_replaces_a_previous_mark(self):
        self._post(E0)
        self._post(E1)
        self.assertEqual([str(u) for u in self._marks()], [E1])

    def test_empty_value_goes_back_to_automatic(self):
        self._post(E1)
        self._post("")
        self.assertEqual(self._marks(), [])

    def test_rejects_an_evidence_of_another_device(self):
        self._post("5f0c3b0e-0000-4000-8000-0000000000ff")
        self.assertEqual(self._marks(), [])


class PresenterTests(SimpleTestCase):
    def _view(self, points, reuse_start=0, marks=frozenset()):
        inputs = DeviceInputs(
            device_type="desktop", points=points, country="ES",
            reuse_start=reuse_start, reuse_source="second_evidence" if reuse_start is not None else None,
            bios_year=2013,
        )
        return device_impact_view(compute_device(inputs, load_factors(), load_grid()), inputs, set(marks))

    def test_story_widths_and_per_hour_drop(self):
        view = self._view([
            EvidencePoint(E0, datetime(2017, 12, 1), 3696),
            EvidencePoint(E1, datetime(2022, 2, 11), 9439),
        ])
        story = view["story"]
        self.assertLess(story["life1_width"], story["typical_left"])
        self.assertLessEqual(story["life1_width"] + story["life2_width"], 100)
        self.assertEqual(view["per_hour_drop"], 48)
        self.assertEqual(max(s["height"] for s in view["stages"]), 100)
        self.assertTrue(view["timeline"][0]["is_start"])
        self.assertEqual(view["provenance"][0]["label"], "Life 1 hours")

    def test_barely_started_second_life_can_raise_cost_per_hour(self):
        view = self._view([
            EvidencePoint(E0, datetime(2025, 11, 6), 27283),
            EvidencePoint(E1, datetime(2025, 12, 6), 27328),
        ])
        self.assertLessEqual(view["per_hour_drop"], 0)
        self.assertEqual(view["per_hour_rise_cause"], "transport")

    def test_rise_blamed_on_electricity_when_it_outweighs_transport(self):
        inputs = DeviceInputs(
            device_type="desktop", country="ES", reuse_start=0, reuse_source="second_evidence",
            points=[EvidencePoint(E0, datetime(2020, 1, 1), 30000), EvidencePoint(E1, datetime(2024, 1, 1), 40000)],
        )
        impact = compute_device(inputs, load_factors(), load_grid())
        impact.stages["use2"] = 500.0  # far more than the ~3.8 kg van legs
        impact.g_per_hour_total = impact.g_per_hour_life1 * 1.1
        view = device_impact_view(impact, inputs, set())
        self.assertEqual(view["per_hour_rise_cause"], "electricity")

    def test_pending_device_has_single_per_hour_row(self):
        view = self._view([EvidencePoint(E0, datetime(2019, 6, 3), 720)], reuse_start=None)
        self.assertFalse(view["reused"])
        self.assertEqual(len(view["per_hour"]), 1)
        self.assertIsNone(view["per_hour_drop"])


class ReadReuseSignalsTests(TestCase):
    """States and lots stored in the database become reuse signals."""

    def setUp(self):
        from action.models import StateDefinition
        from lot.models import LotTag

        self.institution = Institution.objects.create(name="Signals", country="ES")
        self.device = MagicMock()
        self.device.id = "ereuse24:signals"
        self.device.uuids = [E0, E1]
        StateDefinition.objects.create(institution=self.institution, state="DONATION")
        StateDefinition.objects.create(institution=self.institution, state="DISMANTLE")
        StateDefinition.objects.create(
            institution=self.institution, state="ENTREGADO",
            dte_config={"event_type": "MoveEvent", "disposition": "active"},
        )
        self.salida = LotTag.objects.create(name="Salida", owner=self.institution)
        self.entrada = LotTag.objects.create(name="Entrada", owner=self.institution)

    def _state(self, name, uuid):
        from action.models import State
        State.objects.create(institution=self.institution, state=name, snapshot_uuid=uuid)

    def _signals(self):
        from environmental_impact.reuse import read_reuse_signals
        return read_reuse_signals(self.device, self.institution)

    def test_default_donation_state_is_a_transfer(self):
        self._state("DONATION", E1)
        self.assertEqual(self._signals().transfer_uuid, E1)

    def test_configured_move_event_is_a_transfer(self):
        self._state("ENTREGADO", E0)
        self.assertEqual(self._signals().transfer_uuid, E0)

    def test_latest_state_dismantle_ends_life(self):
        self._state("DONATION", E0)
        self._state("DISMANTLE", E1)
        signals = self._signals()
        self.assertTrue(signals.end_of_life)
        self.assertEqual(signals.transfer_uuid, E0)

    def test_only_outgoing_lots_count(self):
        from lot.models import DeviceLot, Lot

        incoming = Lot.objects.create(name="in", owner=self.institution, type=self.entrada)
        DeviceLot.objects.create(lot=incoming, device_id=self.device.id)
        self.assertIsNone(self._signals().outgoing_since)
        outgoing = Lot.objects.create(name="out", owner=self.institution, type=self.salida)
        DeviceLot.objects.create(lot=outgoing, device_id=self.device.id)
        self.assertEqual(self._signals().outgoing_since, outgoing.created)
