from django.test import SimpleTestCase, override_settings

from environmental_impact.algorithms.ereuse2025.carbon_intensity import (
    get_available_country_choices,
    get_country_label,
    resolve_carbon_intensity_factor,
)


class CountryLabelTests(SimpleTestCase):
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
