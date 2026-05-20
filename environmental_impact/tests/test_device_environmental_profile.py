from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from device.views import DetailsView
from environmental_impact.models import DeviceEnvironmentalProfile
from user.models import Institution, User


class DeviceEnvironmentalProfileViewTests(TestCase):
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
        self.device_id = "ereuse24:test-device"

    def _build_request(self, country_code):
        request = self.factory.post(
            f"/device/{self.device_id}/",
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

        response = DetailsView()._save_environmental_profile(request, self.device_id)

        profile = DeviceEnvironmentalProfile.objects.get(
            device_chid=self.device_id,
            owner=self.institution,
        )
        self.assertEqual(profile.country, "NA")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"/device/{self.device_id}/#environmental_impact")

    def test_save_environmental_profile_empty_value_removes_override(self):
        DeviceEnvironmentalProfile.objects.create(
            device_chid=self.device_id,
            owner=self.institution,
            country="NA",
        )
        request = self._build_request("")

        response = DetailsView()._save_environmental_profile(request, self.device_id)

        self.assertFalse(
            DeviceEnvironmentalProfile.objects.filter(
                device_chid=self.device_id,
                owner=self.institution,
            ).exists()
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"/device/{self.device_id}/#environmental_impact")

    def test_save_environmental_profile_rejects_invalid_country_code(self):
        request = self._build_request("NAM")

        response = DetailsView()._save_environmental_profile(request, self.device_id)

        self.assertFalse(
            DeviceEnvironmentalProfile.objects.filter(
                device_chid=self.device_id,
                owner=self.institution,
            ).exists()
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"/device/{self.device_id}/#environmental_impact")
