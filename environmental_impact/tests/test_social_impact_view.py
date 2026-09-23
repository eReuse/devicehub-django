import uuid
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from device.views import DetailsView
from environmental_impact.social_impact import SocialKeys
from evidence.models import UserProperty
from user.models import Institution, User


class SocialImpactViewTenantTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.institution = Institution.objects.create(name="Institution A")
        self.other_institution = Institution.objects.create(name="Institution B")
        self.user = User.objects.create_user(
            email="manager@example.com",
            institution=self.institution,
            password="testpass123",
        )
        self.evidence_uuid = uuid.uuid4()

    def _build_request(self):
        request = self.factory.post(
            "/product/ereuse24:test-device/",
            {
                "action": "save_social_inclusion",
                "vulnerable_person": "on",
            },
        )
        request.user = self.user
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()
        setattr(request, "_messages", FallbackStorage(request))
        return request

    @patch("device.views.evidence_timeline", return_value=[])
    @patch("device.views.Device")
    def test_vulnerable_flag_does_not_update_another_institution(
        self, mock_device, _mock_timeline
    ):
        other_property = UserProperty.objects.create(
            uuid=self.evidence_uuid,
            key=SocialKeys.VULNERABLE,
            value="no",
            owner=self.other_institution,
            type=UserProperty.Type.USER,
        )
        device = Mock()
        device.last_evidence = SimpleNamespace(uuid=self.evidence_uuid)
        device.uuids = [self.evidence_uuid]
        mock_device.return_value = device
        request = self._build_request()
        view = DetailsView()
        view.request = request

        with patch.object(
            view,
            "_get_owned_device_id",
            return_value="ereuse24:test-device",
        ):
            response = view._save_social_inclusion(
                request,
                "ereuse24:test-device",
            )

        other_property.refresh_from_db()
        self.assertEqual(other_property.value, "no")
        self.assertTrue(
            UserProperty.objects.filter(
                uuid=self.evidence_uuid,
                key=SocialKeys.VULNERABLE,
                value="yes",
                owner=self.institution,
            ).exists()
        )
        self.assertEqual(response.status_code, 302)
