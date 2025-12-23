"""
Carbon intensity module for environmental impact calculations.
This is a stub implementation that provides default carbon intensity values.
"""

# Default carbon intensity factors (g CO2e/kWh) for different countries
DEFAULT_CARBON_INTENSITY = {
    "ES": 250.0,  # Spain default
    "FR": 60.0,   # France
    "DE": 400.0,  # Germany
    "US": 500.0,  # United States
    "GB": 300.0,  # United Kingdom
}


def get_carbon_intensity_factor_from(country_code: str) -> float:
    """
    Get carbon intensity factor for a given country code.

    Args:
        country_code: ISO 2-letter country code (e.g., "ES", "FR", "DE")

    Returns:
        Carbon intensity factor in g CO2e/kWh
    """
    return DEFAULT_CARBON_INTENSITY.get(
        country_code, DEFAULT_CARBON_INTENSITY["ES"]
    )


# For backward compatibility
class carbon_intensity:
    @staticmethod
    def get_carbon_intensity_factor_from(country_code: str) -> float:
        return get_carbon_intensity_factor_from(country_code)
