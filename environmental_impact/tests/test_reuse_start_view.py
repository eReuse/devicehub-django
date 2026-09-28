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
        data = {"action": "save_reuse_start"}
        if value is not None:  # None: an unticked checkbox, which posts nothing
            data["reuse_start"] = value
        request = RequestFactory().post(f"/product/{self.device_id}/", data)
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

    def test_unticked_switch_goes_back_to_automatic(self):
        self._post(E0)
        self._post(None)
        self.assertEqual(self._marks(), [])

    def test_rejects_an_evidence_of_another_device(self):
        self._post("5f0c3b0e-0000-4000-8000-0000000000ff")
        self.assertEqual(self._marks(), [])


class PresenterTests(SimpleTestCase):
    def _view(self, points, reuse_start=0, marks=frozenset(), source="second_evidence"):
        inputs = DeviceInputs(
            device_type="desktop", points=points, country="ES",
            reuse_start=reuse_start, reuse_source=source if reuse_start is not None else None,
            bios_year=2013,
        )
        return device_impact_view(compute_device(inputs, load_factors(), load_grid()), inputs, set(marks))

    def test_story_widths_and_stages(self):
        view = self._view([
            EvidencePoint(E0, datetime(2017, 12, 1), 3696),
            EvidencePoint(E1, datetime(2022, 2, 11), 9439),
        ])
        story = view["story"]
        self.assertLess(story["life1_width"], story["typical_width"])
        self.assertEqual(story["typical_width"], 100.0)  # typical life is the longest bar here
        self.assertLessEqual(story["life1_width"] + story["life2_width"], 100)
        self.assertEqual([t["hours"] for t in story["ticks"]], [0, 5000, 10000, 15000, 20000])
        self.assertEqual(max(s["height"] for s in view["stages"]), 100)
        self.assertTrue(view["timeline"][0]["is_start"])
        self.assertEqual(view["provenance"][0]["label"], "Life 1 hours")

    def test_pending_device_is_not_reused(self):
        view = self._view([EvidencePoint(E0, datetime(2019, 6, 3), 720)], reuse_start=None)
        self.assertFalse(view["reused"])

    def test_single_evidence_marked_by_hand_uses_default_life2(self):
        view = self._view([EvidencePoint(E0, datetime(2026, 1, 5), 1092)], source="mark", marks={E0})
        self.assertTrue(view["single_evidence"])
        self.assertTrue(view["reused_by_mark"])
        self.assertEqual(view["impact"].life2_hours, view["expected_life2_hours"])

    def test_counter_at_zero_is_no_reading(self):
        view = self._view([EvidencePoint(E0, datetime(2025, 1, 23), 0)], source="mark", marks={E0})
        self.assertFalse(view["impact"].life1_measured)
        self.assertFalse(view["timeline"][0]["has_reading"])

    def test_single_evidence_reused_by_state_is_not_a_mark(self):
        view = self._view([EvidencePoint(E0, datetime(2026, 1, 5), 1092)], source="transfer_state")
        self.assertFalse(view["reused_by_mark"])
        self.assertEqual(str(view["reuse_source_label"]), "Transfer state")

    def test_several_evidences_keep_the_picker(self):
        view = self._view([
            EvidencePoint(E0, datetime(2017, 12, 1), 3696),
            EvidencePoint(E1, datetime(2022, 2, 11), 9439),
        ])
        self.assertFalse(view["single_evidence"])

    def test_constants_cite_references_numbered_by_first_use(self):
        method = self._view([EvidencePoint(E0, datetime(2026, 1, 5), 1092)])["method"]
        numbers = [r["n"] for r in method["references"]]
        self.assertEqual(numbers, list(range(1, len(numbers) + 1)))
        cited = [n for c in method["constants"] for n in c["refs"]]
        self.assertEqual(sorted(set(cited)), numbers)  # nothing listed that no constant cites
        self.assertTrue(method["references"][0]["title"].startswith("ADEME Base Carbone"))

    def test_device_inputs_exclude_constants(self):
        view = self._view([EvidencePoint(E0, datetime(2026, 1, 5), 1092)])
        labels = [str(p["label"]) for p in view["provenance"]]
        self.assertNotIn("Electricity grid", labels)
        self.assertNotIn("New device footprint", labels)


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
