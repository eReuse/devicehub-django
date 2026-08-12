import uuid

from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch
from device.views import PublicDeviceWebView
from device.tests.test_mock_device import TestDevice
from evidence.models import SystemProperty
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
