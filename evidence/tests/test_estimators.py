from django.test import SimpleTestCase, override_settings

from evidence.estimators import (
    estimate_power_on_hours,
    BatteryCycleEstimator,
    BootCountEstimator,
    DeviceAgeEstimator,
    DEFAULT_POH_ESTIMATOR,
    PohEstimator,
    PowerOnHoursEstimate,
    available_poh_estimators,
    estimate_mobile_power_on_hours,
    get_poh_estimator,
    register_poh_estimator,
)


@register_poh_estimator("test_signals_v0")
class SignalsTestEstimator(PohEstimator):
    """Reads data.signals, which the default implementation ignores."""

    def estimate(self, data):
        hours = (data.get("signals") or {}).get("test_hours")
        return PowerOnHoursEstimate(hours, "HIGH", "test_hours") if hours else None


class PowerOnHoursEstimatorTests(SimpleTestCase):
    def test_no_signals_returns_none(self):
        self.assertIsNone(estimate_power_on_hours({}))
        self.assertIsNone(estimate_power_on_hours(None))

    def test_battery_cycle_wins_over_weaker_signals(self):
        signals = {
            "battery_cycle_count": 200,
            "boot_count": 500,
            "device_age_days": 1000,
        }
        est = estimate_power_on_hours(signals)
        self.assertEqual(est.method, "battery_cycle")
        self.assertEqual(est.confidence, "MEDIUM")
        self.assertEqual(est.hours, 200 * BatteryCycleEstimator.HOURS_PER_CYCLE)

    def test_falls_back_to_boot_count(self):
        est = estimate_power_on_hours({"boot_count": 300, "device_age_days": 1000})
        self.assertEqual(est.method, "boot_count")
        self.assertEqual(est.hours, 300 * BootCountEstimator.HOURS_PER_BOOT)

    def test_falls_back_to_device_age(self):
        est = estimate_power_on_hours({"device_age_days": 365})
        self.assertEqual(est.method, "device_age")
        self.assertEqual(est.confidence, "LOW")
        self.assertEqual(est.hours, int(365 * 24 * DeviceAgeEstimator.DUTY_CYCLE))

    def test_zero_signal_is_treated_as_missing(self):
        # a 0 cycle count is not a usable signal; skip to the next strategy
        est = estimate_power_on_hours({"battery_cycle_count": 0, "boot_count": 10})
        self.assertEqual(est.method, "boot_count")


class PohEstimatorFactoryTests(SimpleTestCase):
    data = {
        "usage": {"battery_cycle_count": 100},
        "signals": {"test_hours": 5000},
    }

    def test_default_implementation_uses_the_usage_chain(self):
        est = estimate_mobile_power_on_hours(self.data)
        self.assertEqual(est.method, "battery_cycle")
        self.assertEqual(est.hours, 100 * BatteryCycleEstimator.HOURS_PER_CYCLE)
        self.assertEqual(get_poh_estimator().name, DEFAULT_POH_ESTIMATOR)

    @override_settings(MOBILE_POH_ESTIMATOR="test_signals_v0")
    def test_setting_switches_the_implementation(self):
        est = estimate_mobile_power_on_hours(self.data)
        self.assertEqual(est.hours, 5000)
        self.assertEqual(est.method, "test_hours")

    def test_explicit_name_wins_over_setting(self):
        est = estimate_mobile_power_on_hours(self.data, get_poh_estimator("test_signals_v0"))
        self.assertEqual(est.hours, 5000)

    def test_unknown_name_is_an_error(self):
        with self.assertRaises(ValueError):
            get_poh_estimator("does_not_exist")

    def test_registered_names_are_listed(self):
        self.assertIn(DEFAULT_POH_ESTIMATOR, available_poh_estimators())
        self.assertIn("test_signals_v0", available_poh_estimators())

    def test_no_data_returns_none(self):
        self.assertIsNone(estimate_mobile_power_on_hours({}))
