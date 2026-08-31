import uuid

from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch

from device.tests.test_mock_device import TestDevice
from evidence.models import SystemProperty
from user.models import User, Institution, InstitutionSettings, LabelVersion


class DeviceSingleLabelViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.test_id = "custom_id:test123"
        self.institution = Institution.objects.create(name="Test Institution")
        self.user = User.objects.create_user(
            email='test@example.com',
            institution=self.institution,
            password='testpass123'
        )
        self.client.login(username='test@example.com', password='testpass123')

    def url_for(self, pk):
        return reverse('device:single_label', kwargs={'pk': pk})

    def use_label_version(self, version):
        settings, _ = InstitutionSettings.objects.get_or_create(
            institution=self.institution
        )
        settings.qr_label_version = version
        settings.save()

    def test_unknown_device_returns_404(self):
        # V2 renders real evidence data and used to blow up on a missing
        # device; V1 only needs the shortid and used to print a bogus label.
        for version in LabelVersion.values:
            with self.subTest(version=version):
                self.use_label_version(version)
                response = self.client.get(self.url_for("custom_id:nonexistent"))
                self.assertEqual(response.status_code, 404)

    def test_device_from_another_institution_returns_404(self):
        other_institution = Institution.objects.create(name="Other Institution")
        other_user = User.objects.create_user(
            email='other@example.com',
            institution=other_institution,
            password='testpass123'
        )
        SystemProperty.objects.create(
            owner=other_institution,
            user=other_user,
            uuid=uuid.uuid4(),
            value=self.test_id,
        )
        for version in LabelVersion.values:
            with self.subTest(version=version):
                self.use_label_version(version)
                response = self.client.get(self.url_for(self.test_id))
                self.assertEqual(response.status_code, 404)

    def test_malformed_pk_returns_404(self):
        response = self.client.get(self.url_for("nocolonhere"))
        self.assertEqual(response.status_code, 404)

    def build_device(self):
        device = TestDevice(id=self.test_id)
        # V2 assembles the label from Evidence getters and from the owner;
        # MagicMock defaults are fine except where a real value is required.
        device.owner = self.institution
        device.last_evidence.get_time_created = lambda: "2026-01-01T00:00:00"
        return device

    @patch('device.views.Device')
    def test_existing_device_renders_label(self, MockDevice):
        for version in LabelVersion.values:
            with self.subTest(version=version):
                MockDevice.return_value = self.build_device()
                self.use_label_version(version)
                response = self.client.get(self.url_for(self.test_id))
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, 'bulk_labels.html')

    @patch('device.views.Device')
    def test_device_is_looked_up_within_the_users_institution(self, MockDevice):
        MockDevice.return_value = TestDevice(id=self.test_id)
        self.client.get(self.url_for(self.test_id))
        self.assertEqual(
            MockDevice.call_args.kwargs['owner'],
            self.institution
        )
