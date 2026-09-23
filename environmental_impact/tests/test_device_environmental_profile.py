import uuid

from django.contrib.messages.storage.fallback import FallbackStorage
from django.http import Http404
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from device.views import DetailsView
from environmental_impact.models import DeviceEnvironmentalProfile
from evidence.models import SystemProperty
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
        SystemProperty.objects.bulk_create(
            [
                SystemProperty(
                    owner=self.institution,
                    user=self.user,
                    uuid=uuid.uuid4(),
                    key="ereuse24",
                    value=self.device_id,
                )
            ]
        )

    def _build_request(self, country_code):
        request = self.factory.post(
            f"/product/{self.device_id}/",
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
        self.assertEqual(response.url, f"/product/{self.device_id}/#environmental_impact")

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
        self.assertEqual(response.url, f"/product/{self.device_id}/#environmental_impact")

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
        self.assertEqual(response.url, f"/product/{self.device_id}/#environmental_impact")

    def test_save_environmental_profile_rejects_unknown_device(self):
        unknown_device_id = "ereuse24:unknown-device"
        request = self._build_request("NA")

        with self.assertRaises(Http404):
            DetailsView()._save_environmental_profile(request, unknown_device_id)

        self.assertFalse(
            DeviceEnvironmentalProfile.objects.filter(
                device_chid=unknown_device_id,
                owner=self.institution,
            ).exists()
        )

    def test_save_environmental_profile_rejects_device_owned_by_other_institution(self):
        other_institution = Institution.objects.create(
            name="Other Institution",
            country="ES",
        )
        other_device_id = "ereuse24:other-device"
        SystemProperty.objects.bulk_create(
            [
                SystemProperty(
                    owner=other_institution,
                    uuid=uuid.uuid4(),
                    key="ereuse24",
                    value=other_device_id,
                )
            ]
        )
        request = self._build_request("NA")

        with self.assertRaises(Http404):
            DetailsView()._save_environmental_profile(request, other_device_id)

        self.assertFalse(
            DeviceEnvironmentalProfile.objects.filter(
                device_chid=other_device_id,
                owner=self.institution,
            ).exists()
        )
