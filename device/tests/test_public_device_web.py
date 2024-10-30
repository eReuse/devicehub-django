from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch
from device.views import PublicDeviceWebView
from device.tests.test_mock_device import TestDevice, TestWebSnapshotDevice


class PublicDeviceWebViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.test_id = "test123"
        self.test_url = reverse('device:device_web',
                                kwargs={'pk': self.test_id})

    def test_url_resolves_correctly(self):
        """Test that the URL is constructed correctly"""
        url = reverse('device:device_web', kwargs={'pk': self.test_id})
        self.assertEqual(url, f'/device/{self.test_id}/public/')

    @patch('device.views.Device')
    def test_html_response(self, MockDevice):
        test_device = TestDevice(id=self.test_id)
        MockDevice.return_value = test_device
        response = self.client.get(self.test_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'device_web.html')

        self.assertContains(response, 'Test Manufacturer')
        self.assertContains(response, 'Test Model')
        self.assertContains(response, 'Computer')
        self.assertContains(response, self.test_id)

        self.assertContains(response, 'CPU')
        self.assertContains(response, 'Intel')
        self.assertContains(response, 'RAM')
        self.assertContains(response, 'Kingston')

    @patch('device.views.Device')
    def test_json_response(self, MockDevice):
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
        self.assertEqual(json_data['components'], test_device.components)

    @patch('device.views.Device')
    def test_websnapshot_device(self, MockDevice):
        test_device = TestWebSnapshotDevice(id=self.test_id)
        MockDevice.return_value = test_device
        response = self.client.get(self.test_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'device_web.html')

        self.assertContains(response, 'http://example.com')
        self.assertContains(response, 'Test Page')
