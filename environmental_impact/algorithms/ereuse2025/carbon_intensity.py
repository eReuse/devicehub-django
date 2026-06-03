import json
import os
from functools import lru_cache

from babel import Locale
from babel.core import UnknownLocaleError


DEFAULT_COUNTRY_CODE = "ES"
DATA_FILENAME = "latest_carbon_intensity_by_country.json"


@lru_cache(maxsize=1)
def get_carbon_intensity_data() -> dict[str, float]:
    data_path = os.path.join(os.path.dirname(__file__), DATA_FILENAME)
    with open(data_path, "r", encoding="utf-8") as data_file:
        raw_data = json.load(data_file)
    return {country_code: float(value) for country_code, value in raw_data.items()}


@lru_cache(maxsize=1)
def get_available_country_codes() -> tuple[str, ...]:
    return tuple(sorted(get_carbon_intensity_data().keys()))


def _normalize_language_code(language_code: str | None) -> str:
    normalized = (language_code or "en").split(".")[0].replace("-", "_")
    parts = normalized.split("_")
    if len(parts) > 1:
        parts[1] = parts[1].upper()
    return "_".join(parts)


@lru_cache(maxsize=16)
def _get_locale(language_code: str) -> Locale:
    normalized_language_code = _normalize_language_code(language_code)
    try:
        return Locale.parse(normalized_language_code)
    except (UnknownLocaleError, ValueError):
        primary_language = normalized_language_code.split("_", 1)[0]
        try:
            return Locale.parse(primary_language)
        except (UnknownLocaleError, ValueError):
            return Locale.parse("en")


def get_country_label(
    country_code: str | None, language_code: str | None = None
) -> str:
    normalized_country_code = (country_code or "").upper()
    if not normalized_country_code:
        return ""

    country_name = _get_locale(language_code or "en").territories.get(
        normalized_country_code
    )
    if not country_name:
        return normalized_country_code
    return f"{country_name} ({normalized_country_code})"


@lru_cache(maxsize=16)
def get_available_country_choices(
    language_code: str | None = None,
) -> tuple[tuple[str, str], ...]:
    choices = (
        (country_code, get_country_label(country_code, language_code))
        for country_code in get_available_country_codes()
    )
    return tuple(sorted(choices, key=lambda choice: choice[1].casefold()))


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
