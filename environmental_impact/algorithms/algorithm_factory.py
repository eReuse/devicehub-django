from __future__ import annotations
from typing import TYPE_CHECKING

from .sample_algo.sample_calculator import SampleEnvironmentalImpactAlgorithm
from .mireia25.mieia25 import (
    SampleEnvironmentalImpactAlgorithm as Mireia25Algorithm
)

if TYPE_CHECKING:
    from .algorithm_interface import EnvironmentImpactAlgorithm


class AlgorithmNames:
    """
    Enum class for the different types of algorithms.
    """

    SAMPLE_CALC = "sample_calc"
    MIREIA25 = "mireia25"

    algorithm_names = {
        SAMPLE_CALC: SampleEnvironmentalImpactAlgorithm(),
        MIREIA25: Mireia25Algorithm()
    }


class FactoryEnvironmentImpactAlgorithm:

    @staticmethod
    def run_environmental_impact_calculation(
        algorithm_name: str = "mireia25",
    ) -> EnvironmentImpactAlgorithm:
        try:
            return AlgorithmNames.algorithm_names[algorithm_name]
        except KeyError:
            raise ValueError(
                "Invalid algorithm name. Valid options are: "
                + ", ".join(AlgorithmNames.algorithm_names.keys())
            )
