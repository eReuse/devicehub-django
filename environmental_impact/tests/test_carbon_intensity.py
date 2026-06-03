from django.test import SimpleTestCase

from environmental_impact.algorithms.ereuse2025.carbon_intensity import (
    get_available_country_choices,
    get_country_label,
)


class CountryLabelTests(SimpleTestCase):
    def test_country_label_disambiguates_alpha_2_codes(self):
        self.assertEqual(get_country_label("NA", "en"), "Namibia (NA)")
        self.assertEqual(get_country_label("NO", "en"), "Norway (NO)")

    def test_available_country_choices_use_country_names_and_codes(self):
        choices = dict(get_available_country_choices("en"))

        self.assertEqual(choices["NA"], "Namibia (NA)")
        self.assertEqual(choices["NO"], "Norway (NO)")
