from __future__ import annotations
from typing import TYPE_CHECKING

from .dummy_algo.dummy_calculator import DummyEnvironmentalImpactAlgorithm

if TYPE_CHECKING:
    from .algorithm_interface import EnvironmentImpactAlgorithm


class AlgorithmNames():
    """
    Enum class for the different types of algorithms.
    """

    DUMMY_CALC = "dummy_calc"

    algorithm_names = {
        DUMMY_CALC: DummyEnvironmentalImpactAlgorithm()
    }


class FactoryEnvironmentImpactAlgorithm():

    @staticmethod
    def run_environmental_impact_calculation(algorithm_name: str) -> EnvironmentImpactAlgorithm:
        try:
            return AlgorithmNames.algorithm_names[algorithm_name]
        except KeyError:
            raise ValueError("Invalid algorithm name. Valid options are: " +
                             ", ".join(AlgorithmNames.algorithm_names.keys()))
