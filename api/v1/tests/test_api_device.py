import uuid
from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch, MagicMock
from datetime import datetime

from user.models import User, Institution
from api.models import Token
from device.tests.test_mock_device import TestDevice
from action.models import State, StateDefinition


class DeviceAPITests(TestCase):
    """Test suite for the GET /api/v1/{device_id}/ endpoint"""

    def setUp(self):
        """Set up test fixtures: institution, user, API token, and test device"""
        self.client = Client()

        # Create institution
        self.institution = Institution.objects.create(
            name="API Test Institution"
        )

        # Create another institution for permission testing
        self.other_institution = Institution.objects.create(
            name="API Other Institution"
        )

        # Create user
        self.user = User.objects.create_user(
            email='test@example.com',
            institution=self.institution,
            password='testpass123'
        )

        # Create user from other institution
        self.other_user = User.objects.create_user(
            email='other@example.com',
            institution=self.other_institution,
            password='testpass123'
        )

        # Create active API token
        self.token = Token.objects.create(
            tag="test_token",
            token=uuid.uuid4(),
            owner=self.user,
            is_active=True
        )

        # Create inactive API token
        self.inactive_token = Token.objects.create(
            tag="inactive_token",
            token=uuid.uuid4(),
            owner=self.user,
            is_active=False
        )

        # Create token for other user
        self.other_token = Token.objects.create(
            tag="other_token",
            token=uuid.uuid4(),
            owner=self.other_user,
            is_active=True
        )

        # Test device ID
        self.device_id = "test123device456"
        self.api_url = f'/api/v1/devices/{self.device_id}/'

    def _create_mock_device(self, device_id=None, owner=None):
        """Helper to create a properly configured TestDevice mock"""
        if device_id is None:
            device_id = self.device_id
        if owner is None:
            owner = self.institution

        test_device = TestDevice(id=device_id)
        test_device.owner = owner
        test_device.pk = device_id

        # Mock components_export method to return proper device data
        test_device.components_export = MagicMock(return_value={
            'ID': device_id,
            'shortId': device_id[:6].upper(),
            'manufacturer': 'Test Manufacturer',
            'model': 'Test Model',
            'serial': 'SN123456',
            'cpu_model': 'Intel i7',
            'cpu_cores': 4,
            'ram_total': '16 GiB',
            'ram_type': 'DDR4',
            'ram_slots': 2,
            'slots_used': 2,
            'drive': 'Samsung SSD (512 GB)',
            'gpu_model': 'NVIDIA GTX 1080',
            'type': 'Laptop',
            'user_properties': "{'test_key': 'test_value'}",
            'current_state': 'TO REPAIR',
            'last_updated': datetime.now()
        })

        # Mock get_current_state
        mock_state = MagicMock(spec=State)
        mock_state.state = 'TO REPAIR'
        test_device.get_current_state = MagicMock(return_value=mock_state)

        return test_device

    @patch('api.v1.devices.Device')
    def test_get_device_details_success(self, MockDevice):
        """Test successful device retrieval with valid authentication"""
        # Setup mock device
        test_device = self._create_mock_device()
        MockDevice.return_value = test_device

        # Make API call with Bearer token
        response = self.client.get(
            self.api_url,
            HTTP_AUTHORIZATION=f'Bearer {self.token.token}'
        )

        # Assert response
        self.assertEqual(response.status_code, 200)
        self.assertIn('application/json', response['Content-Type'])

        # Verify Device was instantiated correctly
        MockDevice.assert_called_once_with(id=self.device_id)

        # Parse JSON response
        json_data = response.json()

        # Verify response structure
        self.assertEqual(json_data['ID'], self.device_id)
        self.assertEqual(json_data['shortId'], self.device_id[:6].upper())
        self.assertEqual(json_data['manufacturer'], 'Test Manufacturer')
        self.assertEqual(json_data['model'], 'Test Model')
        self.assertEqual(json_data['type'], 'Laptop')

    def test_get_device_unauthenticated(self):
        """Test device retrieval without authentication returns 401"""
        response = self.client.get(self.api_url)

        self.assertEqual(response.status_code, 401)

    def test_get_device_invalid_token(self):
        """Test device retrieval with invalid token returns 401"""
        fake_token = uuid.uuid4()

        response = self.client.get(
            self.api_url,
            HTTP_AUTHORIZATION=f'Bearer {fake_token}'
        )

        self.assertEqual(response.status_code, 401)

    def test_get_device_inactive_token(self):
        """Test device retrieval with inactive token returns 401"""
        response = self.client.get(
            self.api_url,
            HTTP_AUTHORIZATION=f'Bearer {self.inactive_token.token}'
        )

        self.assertEqual(response.status_code, 401)

    @patch('api.v1.devices.Device')
    def test_get_device_not_found(self, MockDevice):
        """Test device retrieval when device doesn't exist returns 404"""
        # Setup mock device without last_evidence (simulates non-existent device)
        test_device = TestDevice(id=self.device_id)
        test_device.last_evidence = None
        test_device.owner = self.institution
        MockDevice.return_value = test_device

        response = self.client.get(
            self.api_url,
            HTTP_AUTHORIZATION=f'Bearer {self.token.token}',
        )

        self.assertEqual(response.status_code, 404)
        json_data = response.json()
        self.assertIn('detail', json_data)

    @patch('api.v1.devices.Device')
    def test_get_device_permission_denied(self, MockDevice):
        """Test device retrieval when user doesn't own device returns 403"""
        # Setup mock device owned by different institution
        test_device = self._create_mock_device(owner=self.other_institution)
        MockDevice.return_value = test_device

        # Try to access with first user's token
        response = self.client.get(
            self.api_url,
            HTTP_AUTHORIZATION=f'Bearer {self.token.token}'
        )

        self.assertEqual(response.status_code, 403)
        json_data = response.json()
        self.assertIn('detail', json_data)

    @patch('api.v1.devices.Device')
    def test_device_response_schema_all_fields(self, MockDevice):
        """Test that response contains all required DeviceResponse schema fields"""
        test_device = self._create_mock_device()
        MockDevice.return_value = test_device

        response = self.client.get(
            self.api_url,
            HTTP_AUTHORIZATION=f'Bearer {self.token.token}'
        )

        self.assertEqual(response.status_code, 200)
        json_data = response.json()

        # Verify all required DeviceResponse fields are present
        required_fields = [
            'ID', 'shortId', 'manufacturer', 'model', 'serial',
            'cpu_model', 'cpu_cores', 'ram_total', 'ram_type',
            'ram_slots', 'slots_used', 'drive', 'gpu_model',
            'type', 'user_properties', 'current_state', 'last_updated'
        ]

        for field in required_fields:
            self.assertIn(field, json_data, f"Missing required field: {field}")

        # Verify field types
        self.assertIsInstance(json_data['ID'], str)
        self.assertIsInstance(json_data['shortId'], str)
        self.assertIsInstance(json_data['cpu_cores'], int)
        self.assertIsInstance(json_data['ram_slots'], int)
        self.assertIsInstance(json_data['slots_used'], int)

    @patch('api.v1.devices.Device')
    def test_multiple_users_same_institution(self, MockDevice):
        """Test that users from same institution can access the device"""
        # Create another user in the same institution
        another_user = User.objects.create_user(
            email='another@example.com',
            institution=self.institution,
            password='testpass123'
        )

        another_token = Token.objects.create(
            tag="another_token",
            token=uuid.uuid4(),
            owner=another_user,
            is_active=True
        )

        # Setup mock device
        test_device = self._create_mock_device()
        MockDevice.return_value = test_device

        # Both users should be able to access
        response1 = self.client.get(
            self.api_url,
            HTTP_AUTHORIZATION=f'Bearer {self.token.token}'
        )
        response2 = self.client.get(
            self.api_url,
            HTTP_AUTHORIZATION=f'Bearer {another_token.token}'
        )

        self.assertEqual(response1.status_code, 200)
        self.assertEqual(response2.status_code, 200)

    @patch('api.v1.devices.Device')
    def test_device_shortid_format(self, MockDevice):
        """Test that shortId is correctly formatted (first 6 chars uppercase)"""
        test_device = self._create_mock_device()
        MockDevice.return_value = test_device

        response = self.client.get(
            self.api_url,
            HTTP_AUTHORIZATION=f'Bearer {self.token.token}'
        )

        self.assertEqual(response.status_code, 200)
        json_data = response.json()

        # Verify shortId format
        self.assertEqual(len(json_data['shortId']), 6)
        self.assertTrue(json_data['shortId'].isupper())
        self.assertEqual(json_data['shortId'], self.device_id[:6].upper())
