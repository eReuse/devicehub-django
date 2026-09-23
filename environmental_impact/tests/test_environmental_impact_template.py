import re
from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.utils import translation


class EnvironmentalImpactTemplateTests(SimpleTestCase):
    def _render(self, is_lot_view):
        impact = SimpleNamespace(
            kg_CO2e={"in_use": 860.075},
            relevant_input_data={
                "energy_kwh": 5884.51,
                "total_energy_kwh": 5884.51,
                "country_code": "ES",
                "carbon_intensity_factor": 146.154,
            },
            docs="",
        )
        with translation.override("es"):
            return render_to_string(
                "partials/environmental_impact_content.html",
                {
                    "impact": impact,
                    "is_lot_view": is_lot_view,
                    "comparison_prefix": "test",
                    "chart_id": "testChart",
                },
            )

    def test_script_numbers_are_not_localized(self):
        for is_lot_view in (False, True):
            html = self._render(is_lot_view)

            # A decimal comma here would be a JavaScript syntax error.
            self.assertIn("const co2kg = 860.075;", html)
            self.assertIn("const energyKwh = 5884.51;", html)

    def test_energy_card_uses_algorithm_energy(self):
        html = self._render(is_lot_view=False)

        self.assertIn("Math.round(energyKwh)", html)
        self.assertIsNone(re.search(r"kwhPerKgCO2", html))
