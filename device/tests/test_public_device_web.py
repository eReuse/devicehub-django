from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch
from device.views import PublicDeviceWebView
from device.tests.test_mock_device import TestDevice, TestWebSnapshotDevice
from user.models import User, Institution  # Import both models


class PublicDeviceWebViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.test_id = "test123"
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

    def test_url_resolves_correctly(self):
        """Test that the URL is constructed correctly"""
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
        self.assertNotContains(response, 'Components')
        self.assertNotContains(response, 'CPU')
        self.assertNotContains(response, 'Intel')
        self.assertNotContains(response, 'RAM')
        self.assertNotContains(response, 'Kingston')

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
        test_device.get_last_evidence()
        mock_instance = MockDevice.return_value
        mock_instance.id = self.test_id
        mock_instance.shortid = self.test_id[:6].upper()
        mock_instance.uuids = []
        mock_instance.hids = ['hid1', 'hid2']
        mock_instance.last_evidence = test_device.last_evidence

        response = self.client.get(
            self.test_url,
            HTTP_ACCEPT='application/json'
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')

        json_data = response.json()
        self.assertEqual(json_data['id'], self.test_id)
        self.assertEqual(json_data['shortid'], self.test_id[:6].upper())
        self.assertEqual(json_data['uuids'], [])
        self.assertEqual(json_data['hids'], ['hid1', 'hid2'])
        self.assertNotIn('components', json_data)
        self.assertNotIn('serial_number', json_data)

    @patch('device.views.Device')
    def test_json_response_authenticated(self, MockDevice):
        test_device = TestDevice(id=self.test_id)
        test_device.get_last_evidence()
        mock_instance = MockDevice.return_value
        mock_instance.id = self.test_id
        mock_instance.shortid = self.test_id[:6].upper()
        mock_instance.uuids = []
        mock_instance.hids = ['hid1', 'hid2']
        mock_instance.last_evidence = test_device.last_evidence
        mock_instance.components = test_device.last_evidence.get_components()
        mock_instance.serial_number = test_device.last_evidence.doc['device']['serialNumber']

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
                'manufacturer': 'Intel'
            },
            {
                'type': 'RAM',
                'size': '8GB',
                'manufacturer': 'Kingston'
            }
        ])
        self.assertEqual(json_data['serial_number'], 'SN123456')
        self.assertEqual(json_data['uuids'], [])
        self.assertEqual(json_data['hids'], ['hid1', 'hid2'])

    @patch('device.views.Device')
    def test_websnapshot_device(self, MockDevice):
        test_device = TestWebSnapshotDevice(id=self.test_id)
        MockDevice.return_value = test_device
        response = self.client.get(self.test_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'device_web.html')

        self.assertContains(response, 'http://example.com')
        self.assertContains(response, 'Test Page')
