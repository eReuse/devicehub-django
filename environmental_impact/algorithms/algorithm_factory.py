from __future__ import annotations
from typing import TYPE_CHECKING

from .sample_algo.sample_calculator import SampleEnvironmentalImpactAlgorithm
from .ereuse2025.ereuse2025 import (
    EReuse2025EnvironmentalImpactAlgorithm as EReuse2025Algorithm
)
from .ereuse2026.ereuse2026 import (
    EReuse2026EnvironmentalImpactAlgorithm as EReuse2026Algorithm
)

if TYPE_CHECKING:
    from .algorithm_interface import EnvironmentImpactAlgorithm


class AlgorithmNames:
    """
    Enum class for the different types of algorithms.
    """

    SAMPLE_CALC = "sample_calc"
    EREUSE2025 = "ereuse2025"
    EREUSE2026 = "ereuse2026"

    algorithm_names = {
        SAMPLE_CALC: SampleEnvironmentalImpactAlgorithm(),
        EREUSE2025: EReuse2025Algorithm(),
        EREUSE2026: EReuse2026Algorithm(),
    }


class FactoryEnvironmentImpactAlgorithm:

    @staticmethod
    def run_environmental_impact_calculation(
        algorithm_name: str = "ereuse2025",
    ) -> EnvironmentImpactAlgorithm:
        try:
            return AlgorithmNames.algorithm_names[algorithm_name]
        except KeyError:
            raise ValueError(
                "Invalid algorithm name. Valid options are: "
                + ", ".join(AlgorithmNames.algorithm_names.keys())
            )
