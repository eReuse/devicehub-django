from dataclasses import dataclass
from django.db import models


@dataclass
class EnvironmentalImpact:
    carbon_saved: float = 0.0
    co2_emissions: float = 0.0
    docs: str = ""
