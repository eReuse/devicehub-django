from environmental_impact.algorithms.algorithm_factory import (
    FactoryEnvironmentImpactAlgorithm,
)
from django.test import TestCase
from environmental_impact.algorithms.sample_algo.sample_calculator import (
    SampleEnvironmentalImpactAlgorithm,
)


class FactoryEnvironmentImpactAlgorithmTests(TestCase):

    def test_valid_algorithm_name(self):
        algorithm = (
            FactoryEnvironmentImpactAlgorithm.run_environmental_impact_calculation(
                "sample_calc"
            )
        )
        self.assertIsInstance(
            algorithm,
            SampleEnvironmentalImpactAlgorithm,
            "Factory should return a SampleEnvironmentalImpactAlgorithm instance",
        )

    def test_invalid_algorithm_name(self):
        with self.assertRaises(ValueError):
            FactoryEnvironmentImpactAlgorithm.run_environmental_impact_calculation(
                "invalid_calc"
            )
