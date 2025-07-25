import pickle
import os


def get_carbon_intensity_factor_from(country_code: str) -> float:
    """
    Get carbon intensity factor for the device's location.

    Args:
        device: Device object

    Returns:
        Carbon intensity factor in gCO2/kWh
    """
    carbon_intensity_data = pickle.load(
        open(
            os.path.join(os.path.dirname(__file__), "carbon_intensity_data.pkl"),
            "rb",
        )
    )
    carbon_intensity_value = carbon_intensity_data.get(country_code)
    if carbon_intensity_value is not None:
        return carbon_intensity_value
    else:
        raise ValueError(f"Unknown country code: {country_code}")
