from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, TestCase

from environmental_impact.models import DeviceEnvironmentalProfile
from lot.views import LotEnvironmentalImpactView
from user.models import Institution, User


class LotEnvironmentalImpactViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.institution = Institution.objects.create(
            name="Test Institution",
            country="ES",
        )
        self.user = User.objects.create_user(
            email="test@example.com",
            institution=self.institution,
            password="testpass123",
        )

    @patch("lot.views.Device")
    def test_get_devices_with_evidence_initializes_devices_with_owner(self, mock_device):
        request = self.factory.get("/lot/1/environmental-impact")
        request.user = self.user

        lot = SimpleNamespace(
            devicelot_set=SimpleNamespace(
                all=lambda: SimpleNamespace(
                    values_list=lambda *args, **kwargs: SimpleNamespace(
                        distinct=lambda: ["dev-1", "dev-2"]
                    )
                )
            )
        )

        device_with_evidence = SimpleNamespace(last_evidence=True)
        device_with_evidence.initial = lambda: None
        device_without_evidence = SimpleNamespace(last_evidence=False)
        device_without_evidence.initial = lambda: None
        mock_device.side_effect = [device_with_evidence, device_without_evidence]

        view = LotEnvironmentalImpactView()
        view.request = request
        view.lot = lot

        devices = view._get_devices_with_evidence()

        self.assertEqual(devices, [device_with_evidence])
        mock_device.assert_any_call(id="dev-1", owner=self.institution)
        mock_device.assert_any_call(id="dev-2", owner=self.institution)

    def _view(self):
        request = self.factory.get("/lot/1/environmental-impact")
        request.user = self.user
        view = LotEnvironmentalImpactView()
        view.request = request
        return view

    def _profile(self, device_chid, country):
        DeviceEnvironmentalProfile.objects.create(
            device_chid=device_chid,
            owner=self.institution,
            country=country,
        )

    def test_lot_country_override_when_every_device_shares_it(self):
        devices = [SimpleNamespace(id="dev-1"), SimpleNamespace(id="dev-2")]
        self._profile("dev-1", "NA")
        self._profile("dev-2", "NA")

        self.assertEqual(self._view()._get_lot_country_override(devices), "NA")

    def test_lot_country_override_empty_when_some_devices_use_default(self):
        devices = [SimpleNamespace(id="dev-1"), SimpleNamespace(id="dev-2")]
        self._profile("dev-1", "FR")

        self.assertEqual(self._view()._get_lot_country_override(devices), "")

    def test_lot_country_override_empty_when_overrides_differ(self):
        devices = [SimpleNamespace(id="dev-1"), SimpleNamespace(id="dev-2")]
        self._profile("dev-1", "NA")
        self._profile("dev-2", "PL")

        self.assertEqual(self._view()._get_lot_country_override(devices), "")
