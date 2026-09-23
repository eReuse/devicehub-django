from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from environmental_impact.models import DeviceEnvironmentalProfile
from lot.models import Lot, LotTag, DeviceLot
from lot.views import LotEnvironmentalImpactView
from user.models import Institution, User


class LotEnvironmentalProfileViewTests(TestCase):
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
        self.tag = LotTag.objects.create(name="Test Tag", owner=self.institution)
        self.lot = Lot.objects.create(name="Lot 1", owner=self.institution, type=self.tag)
        self.device_id = "ereuse24:test-device"
        self.other_device_id = "ereuse24:test-device-2"
        DeviceLot.objects.create(lot=self.lot, device_id=self.device_id)
        DeviceLot.objects.create(lot=self.lot, device_id=self.other_device_id)

    def _build_request(self, country_code):
        request = self.factory.post(
            f"/lot/{self.lot.pk}/environmental-impact",
            {
                "action": "save_environmental_profile",
                "country_code": country_code,
            },
        )
        request.user = self.user

        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()

        setattr(request, "_messages", FallbackStorage(request))
        return request

    def test_save_environmental_profile_creates_override(self):
        request = self._build_request("na")
        view = LotEnvironmentalImpactView()
        view.request = request

        response = view._save_environmental_profile(request, self.lot.pk)

        profile = DeviceEnvironmentalProfile.objects.get(
            device_chid=self.device_id,
            owner=self.institution,
        )
        self.assertEqual(profile.country, "NA")
        self.assertTrue(
            DeviceEnvironmentalProfile.objects.filter(
                device_chid=self.other_device_id,
                owner=self.institution,
                country="NA",
            ).exists()
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"/lot/{self.lot.pk}/environmental-impact")

    def test_save_environmental_profile_empty_value_removes_override(self):
        DeviceEnvironmentalProfile.objects.create(
            device_chid=self.device_id,
            owner=self.institution,
            country="NA",
        )
        DeviceEnvironmentalProfile.objects.create(
            device_chid=self.other_device_id,
            owner=self.institution,
            country="NA",
        )
        request = self._build_request("")
        view = LotEnvironmentalImpactView()
        view.request = request

        response = view._save_environmental_profile(request, self.lot.pk)

        self.assertFalse(
            DeviceEnvironmentalProfile.objects.filter(
                device_chid__in=[self.device_id, self.other_device_id],
                owner=self.institution,
            ).exists()
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"/lot/{self.lot.pk}/environmental-impact")
