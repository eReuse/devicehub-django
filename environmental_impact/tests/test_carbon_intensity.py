import json
import tempfile
from pathlib import Path
from unittest.mock import mock_open, patch

from django.test import SimpleTestCase, override_settings

from environmental_impact.algorithms.ereuse2025.carbon_intensity import (
    CarbonIntensityDataError,
    get_available_country_choices,
    get_available_country_codes,
    get_carbon_intensity_data,
    get_country_label,
    resolve_carbon_intensity_factor,
)
from environmental_impact.algorithms.ereuse2025.get_owid_energy_data import (
    save_latest_carbon_intensity_data,
)


class CountryLabelTests(SimpleTestCase):
    def tearDown(self):
        get_carbon_intensity_data.cache_clear()
        get_available_country_codes.cache_clear()
        get_available_country_choices.cache_clear()

    def test_country_label_disambiguates_alpha_2_codes(self):
        self.assertEqual(get_country_label("NA", "en"), "Namibia (NA)")
        self.assertEqual(get_country_label("NO", "en"), "Norway (NO)")

    def test_available_country_choices_use_country_names_and_codes(self):
        choices = dict(get_available_country_choices("en"))

        self.assertEqual(choices["NA"], "Namibia (NA)")
        self.assertEqual(choices["NO"], "Norway (NO)")

    @override_settings(ENVIRONMENTAL_IMPACT_DEFAULT_COUNTRY="FR")
    def test_configured_country_is_used_as_default(self):
        factor, warning = resolve_carbon_intensity_factor(None)

        self.assertEqual(factor, 44.179)
        self.assertIsNone(warning)

    def test_missing_versioned_data_file_raises_clear_error(self):
        get_carbon_intensity_data.cache_clear()

        with patch("builtins.open", side_effect=FileNotFoundError), self.assertLogs(
            "environmental_impact.algorithms.ereuse2025.carbon_intensity",
            level="ERROR",
        ), self.assertRaisesRegex(
            CarbonIntensityDataError,
            "Unable to load versioned carbon-intensity data",
        ):
            get_carbon_intensity_data()

    def test_invalid_versioned_json_raises_clear_error(self):
        get_carbon_intensity_data.cache_clear()

        with patch("builtins.open", mock_open(read_data="{broken")), self.assertLogs(
            "environmental_impact.algorithms.ereuse2025.carbon_intensity",
            level="ERROR",
        ), self.assertRaisesRegex(
            CarbonIntensityDataError,
            "Unable to load versioned carbon-intensity data",
        ):
            get_carbon_intensity_data()

    @override_settings(ENVIRONMENTAL_IMPACT_DEFAULT_COUNTRY="FR")
    def test_missing_configured_default_country_raises_clear_error(self):
        with patch(
            "environmental_impact.algorithms.ereuse2025.carbon_intensity."
            "get_carbon_intensity_data",
            return_value={"ES": 146.154},
        ), self.assertRaisesRegex(
            CarbonIntensityDataError,
            "Configured default country 'FR' is missing",
        ):
            resolve_carbon_intensity_factor(None)


class CarbonIntensityGeneratorTests(SimpleTestCase):
    def test_generator_replaces_output_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "carbon.json"
            output_path.write_text('{"ES": 1}', encoding="utf-8")

            with patch(
                "environmental_impact.algorithms.ereuse2025.get_owid_energy_data."
                "fetch_latest_carbon_intensity_data",
                return_value={"ES": 146.154, "FR": 44.179},
            ):
                result = save_latest_carbon_intensity_data(str(output_path))

            self.assertEqual(result, str(output_path))
            self.assertEqual(
                json.loads(output_path.read_text(encoding="utf-8")),
                {"ES": 146.154, "FR": 44.179},
            )
            self.assertEqual(list(Path(directory).iterdir()), [output_path])

    def test_interrupted_generation_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "carbon.json"
            original_content = '{"ES": 1}'
            output_path.write_text(original_content, encoding="utf-8")

            with patch(
                "environmental_impact.algorithms.ereuse2025.get_owid_energy_data."
                "fetch_latest_carbon_intensity_data",
                return_value={"ES": 146.154},
            ), patch(
                "environmental_impact.algorithms.ereuse2025.get_owid_energy_data."
                "json.dump",
                side_effect=RuntimeError("interrupted"),
            ):
                with self.assertRaises(RuntimeError):
                    save_latest_carbon_intensity_data(str(output_path))

            self.assertEqual(
                output_path.read_text(encoding="utf-8"),
                original_content,
            )
            self.assertEqual(list(Path(directory).iterdir()), [output_path])
