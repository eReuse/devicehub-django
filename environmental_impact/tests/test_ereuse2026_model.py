import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from environmental_impact.algorithms.ereuse2026.ereuse2026 import (
    EReuse2026EnvironmentalImpactAlgorithm,
    bios_year_from_components,
    load_factors,
    load_grid,
)
from environmental_impact.algorithms.ereuse2026.model import (
    DeviceInputs,
    EvidencePoint,
    GridSeries,
    UnsupportedDevice,
    aggregate_lot,
    compute_device,
)
from environmental_impact.algorithms.ereuse2025.lifecycle_models import DiskMetadata, EvidenceData
from environmental_impact.reuse import resolve_reuse_start


def point(uuid, date, poh, disk_changed=False):
    return EvidencePoint(uuid=uuid, date=datetime.fromisoformat(date), poh=poh, disk_changed=disk_changed)


def optiplex_746(**overrides):
    """Device #746 of the thesis dataset (Dell OptiPlex 7010, Receptor 50)."""
    kwargs = dict(
        device_type="desktop",
        points=[point("e0", "2017-12-01", 3696), point("e1", "2022-02-11", 9439)],
        country="ES",
        reuse_start=0,
        reuse_source="second_evidence",
        bios_year=2013,
    )
    kwargs.update(overrides)
    return DeviceInputs(**kwargs)


class ReusedDeviceTests(unittest.TestCase):
    """Reproduces the figures shown in the device-page mockup."""

    def setUp(self):
        self.impact = compute_device(optiplex_746(), load_factors(), load_grid())

    def test_status_and_hours(self):
        self.assertEqual(self.impact.status, "reused")
        self.assertEqual(self.impact.life1_hours, 3696)
        self.assertTrue(self.impact.life1_measured)
        self.assertEqual(self.impact.life2_hours, 9439 - 3696)
        self.assertTrue(self.impact.life2_measured)

    def test_avoided_is_new_device_minus_refurbisher_overhead(self):
        # 169 kg Base Carbone desktop - 4.5 recycling credit - 3.8 kg van legs
        self.assertAlmostEqual(self.impact.avoided, 160.7, delta=0.1)
        self.assertAlmostEqual(self.impact.avoided, self.impact.s3 - self.impact.s2)
        self.assertLess(self.impact.avoided_low, self.impact.avoided_high)

    def test_current_owner_carries_unused_manufacturing(self):
        self.assertAlmostEqual(self.impact.unused_share, 1 - 3696 / 20998, places=6)
        self.assertAlmostEqual(self.impact.attributed_kg, 80.9, delta=0.2)
        self.assertAlmostEqual(self.impact.new_equivalent_kg, 169.0, places=1)

    def test_second_life_halves_footprint_per_hour(self):
        self.assertAlmostEqual(self.impact.g_per_hour_life1, 58, delta=1)
        self.assertAlmostEqual(self.impact.g_per_hour_total, 30, delta=1)

    def test_calendar_lifetime_from_bios(self):
        self.assertAlmostEqual(self.impact.lifetime_years, 8.6, delta=0.1)

    def test_running_it_uses_measured_hours_per_year(self):
        self.assertTrue(self.impact.hours_per_year_measured)
        self.assertAlmostEqual(self.impact.hours_per_year, 5743 / ((datetime(2022, 2, 11) - datetime(2017, 12, 1)).days / 365.25), delta=1)

    def test_avoided_does_not_depend_on_the_grid(self):
        south_africa = compute_device(optiplex_746(country="ZA"), load_factors(), load_grid())
        self.assertAlmostEqual(south_africa.avoided, self.impact.avoided, places=6)
        self.assertGreater(south_africa.cost_second_user, self.impact.cost_second_user)


class EdgeCaseTests(unittest.TestCase):
    def test_single_evidence_without_mark_is_pending(self):
        impact = compute_device(
            optiplex_746(points=[point("e0", "2019-06-03", 720)], reuse_start=None, reuse_source=None),
            load_factors(), load_grid(),
        )
        self.assertEqual(impact.status, "pending")
        self.assertIsNone(impact.avoided)
        self.assertIsNone(impact.attributed_kg)
        self.assertEqual(impact.stages["use2"], 0)

    def test_marked_single_evidence_projects_second_life(self):
        impact = compute_device(
            optiplex_746(points=[point("e0", "2019-06-03", 720)], reuse_start=0, reuse_source="mark"),
            load_factors(), load_grid(),
        )
        self.assertEqual(impact.status, "reused")
        self.assertFalse(impact.life2_measured)
        self.assertEqual(impact.life2_hours, 3600)

    def test_unusable_life1_reading_counts_device_as_new(self):
        impact = compute_device(
            optiplex_746(points=[point("e0", "2017-12-01", 2), point("e1", "2022-02-11", 900)]),
            load_factors(), load_grid(),
        )
        self.assertFalse(impact.life1_measured)
        self.assertEqual(impact.life1_hours, 20998)
        self.assertIsNone(impact.unused_share)
        self.assertAlmostEqual(impact.attributed_kg, impact.new_equivalent_kg)

    def test_span_with_disk_swap_is_not_measured(self):
        impact = compute_device(
            optiplex_746(points=[point("e0", "2017-12-01", 3696), point("e1", "2022-02-11", 120, disk_changed=True)]),
            load_factors(), load_grid(),
        )
        self.assertFalse(impact.life2_measured)
        self.assertEqual(impact.life2_disk_swaps, 1)
        self.assertEqual(impact.life2_hours, 3600)

    def test_device_past_typical_life_carries_only_delivery(self):
        impact = compute_device(
            optiplex_746(points=[point("e0", "2019-06-03", 25000), point("e1", "2020-06-03", 26000)]),
            load_factors(), load_grid(),
        )
        self.assertEqual(impact.unused_share, 0)
        self.assertAlmostEqual(impact.attributed_kg, 11.3 / 1000 * 400 * 0.842, places=6)

    def test_servers_are_not_covered(self):
        with self.assertRaises(UnsupportedDevice):
            compute_device(optiplex_746(device_type="server"), load_factors(), load_grid())

    def test_unknown_country_falls_back_with_warning(self):
        impact = compute_device(optiplex_746(country="QQ"), load_factors(), load_grid())
        self.assertEqual(impact.country, "ES")
        self.assertTrue(impact.warnings)


class MobileTests(unittest.TestCase):
    """Phones and tablets: yearly energy over estimated powered-on hours."""

    def phone(self, **overrides):
        kwargs = dict(
            device_type="smartphone",
            points=[point("p0", "2023-03-01", 9000), point("p1", "2024-03-01", 15500)],
            country="ES",
            reuse_start=0,
            reuse_source="second_evidence",
            hours_method="android_estimate",
        )
        kwargs.update(overrides)
        return DeviceInputs(**kwargs)

    def test_phone_uses_yearly_energy(self):
        impact = compute_device(self.phone(), load_factors(), load_grid())
        kwh_per_hour = 7.0 / 6574.5
        self.assertAlmostEqual(impact.kwh_per_year, impact.hours_per_year * kwh_per_hour)
        self.assertTrue(impact.hours_estimated)
        self.assertIn("Android", impact.provenance[0].source)

    def test_phone_avoided_has_no_recycling_credit(self):
        impact = compute_device(self.phone(), load_factors(), load_grid())
        legs = 0.17 / 1000 * 400 * 0.842
        self.assertAlmostEqual(impact.avoided, 26.5 + 1.06 + 5.27 - legs, places=6)  # Base Carbone posts; total rounds to 32.8
        self.assertIsNone(impact.technician_hours)

    def test_phone_unused_share_uses_three_year_first_life(self):
        impact = compute_device(self.phone(), load_factors(), load_grid())
        self.assertAlmostEqual(impact.unused_share, 1 - 9000 / 19724)

    def test_factor_set_without_tablet_falls_back_with_warning(self):
        impact = compute_device(self.phone(device_type="tablet", factor_set="ademe_arcep_2025"), load_factors(), load_grid())
        self.assertEqual(impact.factor_set, "base_carbone")
        self.assertTrue(any("Base Carbone" in w for w in impact.warnings))

    def test_ademe_2025_is_available_for_smartphones(self):
        impact = compute_device(self.phone(factor_set="ademe_arcep_2025"), load_factors(), load_grid())
        self.assertAlmostEqual(impact.new_equivalent_kg, 79.27, places=2)

    def test_lot_counts_unknown_labour(self):
        impact = compute_device(self.phone(), load_factors(), load_grid())
        lot = aggregate_lot([impact])
        self.assertEqual((lot.technician_hours, lot.technician_hours_unknown), (0.0, 1))


class GridSeriesTests(unittest.TestCase):
    def test_years_outside_series_are_clamped(self):
        grid = GridSeries({"ES": {"2020": 0.2, "2021": 0.1}})
        self.assertEqual(grid.at("ES", 1999), 0.2)
        self.assertEqual(grid.at("ES", 2030), 0.1)
        self.assertAlmostEqual(grid.mean("ES", 2019, 2022), (0.2 + 0.2 + 0.1 + 0.1) / 4)

    def test_country_without_series_uses_latest_value(self):
        grid = GridSeries({"ES": {"2020": 0.2}}, latest={"XK": 900.0})
        self.assertEqual(grid.resolve("xk"), ("XK", None))
        self.assertEqual(grid.at("XK", 2010), 0.9)


class ReuseStartTests(unittest.TestCase):
    def test_mark_wins_over_second_evidence(self):
        self.assertEqual(resolve_reuse_start(["a", "b", "c"], {"b"}), (1, "mark"))

    def test_second_evidence_starts_reuse_at_intake(self):
        self.assertEqual(resolve_reuse_start(["a", "b"], set()), (0, "second_evidence"))

    def test_single_evidence_without_mark_is_not_reused(self):
        self.assertEqual(resolve_reuse_start(["a"], set()), (None, None))


class DeviceTypeTests(unittest.TestCase):
    def test_chassis_names_map_to_model_types(self):
        from environmental_impact.algorithms.ereuse2026.ereuse2026 import model_device_type
        cases = {
            "Desktop": "desktop", "Mini-tower": "desktop", "Microtower": "desktop", "All-in-one": "desktop",
            "Laptop": "laptop", "Netbook": "laptop", "Notebook": "laptop", "Convertible": "laptop",
            "Tablet": "tablet", "Detachable": "tablet", "Smartphone": "smartphone",
            "Server": None, "GraphicCard": None, "": None, None: None,
        }
        for raw, expected in cases.items():
            self.assertEqual(model_device_type(raw), expected, raw)


class BiosYearTests(unittest.TestCase):
    def test_parses_common_date_formats(self):
        for raw in ("12/24/2012", "2012-12-24", "A04 12/24/2012"):
            self.assertEqual(bios_year_from_components([{"type": "Motherboard", "biosDate": raw}]), 2012)

    def test_missing_or_garbage(self):
        self.assertIsNone(bios_year_from_components([{"type": "Motherboard", "biosDate": "N/A"}]))
        self.assertIsNone(bios_year_from_components([{"type": "Storage"}]))
        self.assertIsNone(bios_year_from_components(None))


class LotAggregateTests(unittest.TestCase):
    def test_sums_reused_and_counts_pending(self):
        reused = compute_device(optiplex_746(), load_factors(), load_grid())
        pending = compute_device(
            optiplex_746(points=[point("e0", "2019-06-03", 720)], reuse_start=None, reuse_source=None),
            load_factors(), load_grid(),
        )
        lot = aggregate_lot([reused, reused, pending], unsupported=1)
        self.assertEqual((lot.devices, lot.reused, lot.pending, lot.unsupported), (3, 2, 1, 1))
        self.assertAlmostEqual(lot.avoided, 2 * reused.avoided)
        self.assertEqual(lot.life2_hours_measured, 2 * reused.life2_hours)
        self.assertAlmostEqual(lot.cost_with_new, 2 * (reused.s3 - reused.s1))
        self.assertAlmostEqual(lot.stages["manufacture"], 3 * reused.stages["manufacture"])


class AdapterTests(unittest.TestCase):
    """The Django-facing algorithm builds model inputs from a device's evidences."""

    def _device(self, device_type="Desktop"):
        device = Mock()
        device.id = "dev"
        device.type = device_type
        device.uuids = ["e0", "e1"]
        device.owner = None
        device.last_evidence.get_components.return_value = [{"type": "Motherboard", "biosDate": "05/14/2013"}]
        return device

    @patch("environmental_impact.algorithms.ereuse2026.ereuse2026.read_reuse_marks", return_value=set())
    @patch("environmental_impact.algorithms.ereuse2026.ereuse2026.common.get_device_country_code", return_value="ES")
    @patch("environmental_impact.algorithms.ereuse2026.ereuse2026.get_evidences_data_from_device")
    def test_device_impact_from_evidences(self, evidences, _country, _marks):
        disk = DiskMetadata("S1", "M", "X")
        evidences.return_value = [
            EvidenceData("e0", 0, 3696, disk, date=datetime(2017, 12, 1)),
            EvidenceData("e1", 1, 9439, disk, date=datetime(2022, 2, 11)),
        ]
        env = EReuse2026EnvironmentalImpactAlgorithm().get_device_environmental_impact(self._device())
        self.assertEqual(env.model.status, "reused")
        self.assertEqual(env.model.reuse_source, "second_evidence")
        self.assertAlmostEqual(env.model.lifetime_years, 8.6, delta=0.1)
        self.assertEqual(env.relevant_input_data["total_usage_time"], 9439)
        self.assertAlmostEqual(env.kg_CO2e["in_use"], env.model.use_phase_kg)

    def test_unsupported_type_raises(self):
        with self.assertRaises(UnsupportedDevice):
            EReuse2026EnvironmentalImpactAlgorithm().compute(self._device("Server"))

    @patch("environmental_impact.algorithms.ereuse2026.ereuse2026.read_reuse_marks", return_value=set())
    @patch("environmental_impact.algorithms.ereuse2026.ereuse2026.common.get_device_country_code", return_value="ES")
    @patch("environmental_impact.algorithms.ereuse2026.ereuse2026.get_evidences_data_from_device")
    def test_lot_skips_unsupported_devices(self, evidences, _country, _marks):
        disk = DiskMetadata("S1", "M", "X")
        evidences.return_value = [
            EvidenceData("e0", 0, 3696, disk, date=datetime(2017, 12, 1)),
            EvidenceData("e1", 1, 9439, disk, date=datetime(2022, 2, 11)),
        ]
        env = EReuse2026EnvironmentalImpactAlgorithm().get_lot_environmental_impact(
            [self._device(), self._device("Server")]
        )
        self.assertEqual((env.lot.devices, env.lot.reused, env.lot.unsupported), (1, 1, 1))
