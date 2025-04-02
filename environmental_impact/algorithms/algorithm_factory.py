from __future__ import annotations
from typing import TYPE_CHECKING

from .sample_algo.sample_calculator import SampleEnvironmentalImpactAlgorithm

if TYPE_CHECKING:
    from .algorithm_interface import EnvironmentImpactAlgorithm


class AlgorithmNames:
    """
    Enum class for the different types of algorithms.
    """

    SAMPLE_CALC = "sample_calc"

    algorithm_names = {SAMPLE_CALC: SampleEnvironmentalImpactAlgorithm()}


class FactoryEnvironmentImpactAlgorithm:

    @staticmethod
    def run_environmental_impact_calculation(
        algorithm_name: str = "sample_calc",
    ) -> EnvironmentImpactAlgorithm:
        try:
            return AlgorithmNames.algorithm_names[algorithm_name]
        except KeyError:
            raise ValueError(
                "Invalid algorithm name. Valid options are: "
                + ", ".join(AlgorithmNames.algorithm_names.keys())
            )
