from django.test import SimpleTestCase

from evidence.estimators import (
    estimate_power_on_hours,
    BatteryCycleEstimator,
    BootCountEstimator,
    DeviceAgeEstimator,
)


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
