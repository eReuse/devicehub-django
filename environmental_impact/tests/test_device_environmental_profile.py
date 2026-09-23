import uuid
from datetime import timedelta

from django.contrib.messages.storage.fallback import FallbackStorage
from django.http import Http404
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.utils import timezone

from device.views import DetailsView
from environmental_impact.models import DeviceEnvironmentalProfile
from evidence.models import RootAlias, SystemProperty
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


class DeviceEnvironmentalProfileAliasTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(
            name="Alias Institution",
            country="ES",
        )
        now = timezone.now()
        for device_id in ("ereuse24:A", "ereuse24:B"):
            RootAlias.objects.create(
                owner=self.institution,
                alias=device_id,
                root=device_id,
                created=now,
                updated=now,
            )

    def test_profile_moves_to_new_root(self):
        DeviceEnvironmentalProfile.objects.create(
            owner=self.institution,
            device_chid="ereuse24:A",
            country="NA",
        )

        RootAlias.set_alias(
            self.institution,
            "ereuse24:A",
            "ereuse24:B",
        )

        profile = DeviceEnvironmentalProfile.objects.get(owner=self.institution)
        self.assertEqual(profile.device_chid, "ereuse24:B")
        self.assertEqual(profile.country, "NA")

    def test_profile_collision_keeps_most_recent(self):
        old_profile = DeviceEnvironmentalProfile.objects.create(
            owner=self.institution,
            device_chid="ereuse24:A",
            country="ES",
        )
        new_profile = DeviceEnvironmentalProfile.objects.create(
            owner=self.institution,
            device_chid="ereuse24:B",
            country="NA",
        )
        now = timezone.now()
        DeviceEnvironmentalProfile.objects.filter(pk=old_profile.pk).update(
            updated=now,
        )
        DeviceEnvironmentalProfile.objects.filter(pk=new_profile.pk).update(
            updated=now + timedelta(milliseconds=1),
        )

        RootAlias.set_alias(
            self.institution,
            "ereuse24:A",
            "ereuse24:B",
        )

        profiles = DeviceEnvironmentalProfile.objects.filter(
            owner=self.institution,
        )
        self.assertEqual(profiles.count(), 1)
        self.assertEqual(profiles.get().device_chid, "ereuse24:B")
        self.assertEqual(profiles.get().country, "NA")

    def test_profile_returns_to_device_when_solo_alias_is_removed(self):
        RootAlias.set_alias(
            self.institution,
            "ereuse24:A",
            "custom_id:solo",
        )
        DeviceEnvironmentalProfile.objects.create(
            owner=self.institution,
            device_chid="custom_id:solo",
            country="NA",
        )

        RootAlias.set_alias(
            self.institution,
            "ereuse24:A",
            "ereuse24:A",
        )

        profile = DeviceEnvironmentalProfile.objects.get(owner=self.institution)
        self.assertEqual(profile.device_chid, "ereuse24:A")
        self.assertEqual(profile.country, "NA")

    def test_profile_stays_with_shared_root_when_one_alias_leaves(self):
        RootAlias.set_alias(
            self.institution,
            "ereuse24:A",
            "custom_id:shared",
        )
        RootAlias.set_alias(
            self.institution,
            "ereuse24:B",
            "custom_id:shared",
        )
        DeviceEnvironmentalProfile.objects.create(
            owner=self.institution,
            device_chid="custom_id:shared",
            country="NA",
        )

        RootAlias.set_alias(
            self.institution,
            "ereuse24:A",
            "ereuse24:A",
        )

        profile = DeviceEnvironmentalProfile.objects.get(owner=self.institution)
        self.assertEqual(profile.device_chid, "custom_id:shared")
