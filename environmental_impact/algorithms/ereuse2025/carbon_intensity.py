import json
import os
from functools import lru_cache


DEFAULT_COUNTRY_CODE = "ES"
DATA_FILENAME = "latest_carbon_intensity_by_country.json"


@lru_cache(maxsize=1)
def get_carbon_intensity_data() -> dict[str, float]:
    data_path = os.path.join(os.path.dirname(__file__), DATA_FILENAME)
    with open(data_path, "r", encoding="utf-8") as data_file:
        raw_data = json.load(data_file)
    return {country_code: float(value) for country_code, value in raw_data.items()}


def get_carbon_intensity_factor_from(country_code: str) -> float:
    """
    Get carbon intensity factor for a given ISO 3166-1 alpha-2 country code.
    """
    normalized_country_code = (country_code or DEFAULT_COUNTRY_CODE).upper()
    return get_carbon_intensity_data()[normalized_country_code]


def resolve_carbon_intensity_factor(country_code: str | None) -> tuple[float, str | None]:
    normalized_country_code = (country_code or DEFAULT_COUNTRY_CODE).upper()

    try:
        return get_carbon_intensity_factor_from(normalized_country_code), None
    except KeyError:
        fallback_factor = get_carbon_intensity_factor_from(DEFAULT_COUNTRY_CODE)
        warning = (
            f"Unknown country code '{normalized_country_code}'. "
            f"Using {DEFAULT_COUNTRY_CODE} carbon intensity fallback."
        )
        return fallback_factor, warning


class carbon_intensity:
    @staticmethod
    def get_carbon_intensity_factor_from(country_code: str) -> float:
        return get_carbon_intensity_factor_from(country_code)

    @staticmethod
    def resolve_carbon_intensity_factor(country_code: str | None) -> tuple[float, str | None]:
        return resolve_carbon_intensity_factor(country_code)
