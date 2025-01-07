from environmental_impact.algorithms.algorithm_factory import FactoryEnvironmentImpactAlgorithm
from django.test import TestCase
from environmental_impact.algorithms.dummy_calculator import DummyEnvironmentalImpactAlgorithm


class FactoryEnvironmentImpactAlgorithmTests(TestCase):

    def test_valid_algorithm_name(self):
        algorithm = FactoryEnvironmentImpactAlgorithm.run_environmental_impact_calculation(
            'dummy_calc')
        self.assertIsInstance(algorithm, DummyEnvironmentalImpactAlgorithm,
                              "Factory should return a DummyEnvironmentalImpactAlgorithm instance")

    def test_invalid_algorithm_name(self):
        with self.assertRaises(ValueError):
            FactoryEnvironmentImpactAlgorithm.run_environmental_impact_calculation(
                'invalid_calc')
