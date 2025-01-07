from unittest.mock import patch
import uuid
from django.test import TestCase
from device.models import Device
from environmental_impact.models import EnvironmentalImpact
from environmental_impact.algorithms.dummy_calculator import DummyEnvironmentalImpactAlgorithm
from evidence.models import Evidence


class DummyEnvironmentalImpactAlgorithmTests(TestCase):

    @patch('evidence.models.Evidence.get_doc', return_value={'credentialSubject': {}})
    @patch('evidence.models.Evidence.get_time', return_value=None)
    def setUp(self, mock_get_time, mock_get_doc):
        self.device = Device(id='1')
        evidence = self.device.last_evidence = Evidence(uuid=uuid.uuid4())
        evidence.inxi = True
        evidence.doc = {'credentialSubject': {}}
        self.algorithm = DummyEnvironmentalImpactAlgorithm()

    def test_get_power_on_hours_from_legacy_device(self):
        # TODO is there a way to check that?
        pass

    @patch('evidence.models.Evidence.get_components', return_value=[0, 0, 0, 0, 0, 0, 0, 0, 0, {'time of used': '1y 2d 3h'}])
    def test_get_power_on_hours_from_inxi_device(self, mock_get_components):
        hours = self.algorithm.get_power_on_hours_from(self.device)
        self.assertEqual(
            hours, 8811, "Inxi-parsed devices should correctly compute power-on hours")

    @patch('evidence.models.Evidence.get_components', return_value=[0, 0, 0, 0, 0, 0, 0, 0, 0, {'time of used': '1y 2d 3h'}])
    def test_convert_str_time_to_hours(self, mock_get_components):
        result = self.algorithm.convert_str_time_to_hours('1y 2d 3h', False)
        self.assertEqual(
            result, 8811, "String to hours conversion should match expected output")

    @patch('evidence.models.Evidence.get_components', return_value=[0, 0, 0, 0, 0, 0, 0, 0, 0, {'time of used': '1y 2d 3h'}])
    def test_environmental_impact_calculation(self, mock_get_components):
        impact = self.algorithm.get_device_environmental_impact(self.device)
        self.assertIsInstance(impact, EnvironmentalImpact,
                              "Output should be an EnvironmentalImpact instance")
        expected_co2 = 8811 * 40 * 0.475 / 1000
        self.assertAlmostEqual(impact.co2_emissions, expected_co2,
                               2, "CO2 emissions calculation should be accurate")
