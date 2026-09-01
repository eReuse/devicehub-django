import uuid

from datetime import timedelta

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch
from device.views import PublicDeviceWebView
from device.tests.test_mock_device import TestDevice
from evidence.models import RootAlias, SystemProperty
from user.models import User, Institution


class PublicDeviceWebViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.test_id = "custom_id:test123"
        self.test_url = reverse('device:device_web',
                                kwargs={'pk': self.test_id})
        self.institution = Institution.objects.create(
            name="Test Institution"
        )
        self.user = User.objects.create_user(
            email='test@example.com',
            institution=self.institution,
            password='testpass123'
        )
        # The view resolves the owner from a SystemProperty before building the
        # Device, so the id must exist in the database even though Device itself
        # is mocked.
        self.property_uuid = uuid.uuid4()
        SystemProperty.objects.create(
            owner=self.institution,
            user=self.user,
            uuid=self.property_uuid,
            value=self.test_id,
        )

    def test_url_resolves_correctly(self):
        url = reverse('device:device_web', kwargs={'pk': self.test_id})
        self.assertEqual(url, f'/device/{self.test_id}/public/')

    @patch('device.views.Device')
    def test_html_response_anonymous(self, MockDevice):
        test_device = TestDevice(id=self.test_id)
        MockDevice.return_value = test_device
        response = self.client.get(self.test_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'device_web.html')
        self.assertContains(response, 'Test Manufacturer')
        self.assertContains(response, 'Test Model')
        self.assertContains(response, 'Computer')
        self.assertContains(response, self.test_id)
        self.assertNotContains(response, 'Serial Number')
        self.assertNotContains(response, 'serialNumber')

    @patch('device.views.Device')
    def test_html_response_authenticated(self, MockDevice):
        test_device = TestDevice(id=self.test_id)
        MockDevice.return_value = test_device
        self.client.login(username='test@example.com', password='testpass123')
        response = self.client.get(self.test_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'device_web.html')
        self.assertContains(response, 'Test Manufacturer')
        self.assertContains(response, 'Test Model')
        self.assertContains(response, 'Computer')
        self.assertContains(response, self.test_id)
        self.assertContains(response, 'Serial Number')
        self.assertContains(response, 'Components')
        self.assertContains(response, 'CPU')
        self.assertContains(response, 'Intel')
        self.assertContains(response, 'RAM')
        self.assertContains(response, 'Kingston')

    @patch('device.views.Device')
    def test_json_response_anonymous(self, MockDevice):
        test_device = TestDevice(id=self.test_id)
        MockDevice.return_value = test_device
        response = self.client.get(
            self.test_url,
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        json_data = response.json()
        self.assertEqual(json_data['id'], self.test_id)
        self.assertEqual(json_data['shortid'], self.test_id[:6].upper())
        self.assertEqual(json_data['uuids'], [str(self.property_uuid)])
        self.assertEqual(json_data['hids'], [self.test_id])
        self.assertNotIn('serial_number', json_data)
        self.assertNotIn('serialNumber', json_data)

    @patch('device.views.Device')
    def test_json_response_authenticated(self, MockDevice):
        test_device = TestDevice(id=self.test_id)
        MockDevice.return_value = test_device
        self.client.login(username='test@example.com', password='testpass123')
        response = self.client.get(
            self.test_url,
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')

        json_data = response.json()
        self.assertEqual(json_data['id'], self.test_id)
        self.assertEqual(json_data['shortid'], self.test_id[:6].upper())
        self.assertEqual(json_data['components'], [
            {
                'type': 'CPU',
                'model': 'Intel i7',
                'manufacturer': 'Intel',
                'serialNumber': 'SN12345678'
            },
            {
                'type': 'RAM',
                'size': '8GB',
                'manufacturer': 'Kingston',
                'serialNumber': 'SN87654321'
            }
        ])
        self.assertEqual(json_data['serial_number'], 'SN123456')
        self.assertEqual(json_data['uuids'], [str(self.property_uuid)])
        self.assertEqual(json_data['hids'], [self.test_id])


class PublicDeviceWebViewNotFoundTests(TestCase):
    """The view resolves the owner from the id itself, so an id nobody has
    ever registered cannot be rendered."""

    def setUp(self):
        self.client = Client()
        self.unknown_id = "custom_id:ghost"
        self.url = reverse('device:device_web',
                           kwargs={'pk': self.unknown_id})

    def test_unknown_device_returns_404(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)

    def test_unknown_device_returns_404_as_json(self):
        response = self.client.get(self.url, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 404)


class PublicDeviceWebViewOwnerResolutionTests(TestCase):
    """Two institutions can share a value, and the public url names none of
    them, so the owner is the one holding the most recent evidence."""

    shared_value = "ereuse24:aaaaaa"
    canonical_value = "ereuse24:bbbbbb"

    def setUp(self):
        self.older = Institution.objects.create(name="Older")
        self.newer = Institution.objects.create(name="Newer")
        self.view = PublicDeviceWebView()

    def property_for(self, owner, value, created):
        prop = SystemProperty.objects.create(
            owner=owner, uuid=uuid.uuid4(), value=value)
        # created is auto_now_add, so it can only be set afterwards
        SystemProperty.objects.filter(pk=prop.pk).update(created=created)
        return prop

    def test_owner_is_the_one_with_the_most_recent_property(self):
        # inserted first, so an unordered query would pick this one
        self.property_for(
            self.older, self.shared_value, timezone.now() - timedelta(days=1))
        self.property_for(self.newer, self.shared_value, timezone.now())

        self.assertEqual(
            self.view.get_owner_for_device(self.shared_value), self.newer)

    def test_owner_falls_back_to_the_most_recent_root_alias(self):
        for owner, days in [(self.older, 1), (self.newer, 0)]:
            moment = timezone.now() - timedelta(days=days)
            RootAlias.objects.create(
                owner=owner,
                alias=f"custom_id:{owner.name}",
                root=self.canonical_value,
                created=moment,
                updated=moment,
            )

        self.assertEqual(
            self.view.get_owner_for_device(self.canonical_value), self.newer)

    @patch('device.views.Device')
    def test_device_is_built_once_with_the_resolved_owner(self, MockDevice):
        self.property_for(
            self.newer, self.shared_value, timezone.now())
        url = reverse('device:device_web',
                      kwargs={'pk': self.shared_value})

        self.client.get(url)

        self.assertEqual(MockDevice.call_count, 1)
        self.assertEqual(MockDevice.call_args.kwargs['owner'], self.newer)

