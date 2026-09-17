"""Power-on-hours estimation for mobile devices.

A non-root, non-adb Android app cannot read a SMART-style ``power_on_hours``
counter. Instead the app ships whatever raw wear *signals* it can collect
(``data.usage`` of a workbench-android snapshot) and the estimation happens
here, server-side, on purpose:

- the estimator can improve without redeploying the APK to every phone,
- old snapshots can be re-estimated when the algorithm improves,
- it mirrors the PC path, where devicehub derives usage from raw evidence.

Design is a factory over pluggable strategies. Each strategy returns an
estimate or ``None`` when its signal is missing. ``estimate_power_on_hours``
picks the first available strategy in confidence order. Add new strategies
(e.g. a UsageStatsManager-based one) without touching the callers.

The per-cycle / per-boot / duty constants are deliberately rough: for refurb
triage the *relative* ranking of devices matters more than absolute accuracy.
"""

CONFIDENCE_LOW = "LOW"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_HIGH = "HIGH"


class PowerOnHoursEstimate:
    def __init__(self, hours, confidence, method):
        self.hours = int(hours)
        self.confidence = confidence
        self.method = method

    def as_dict(self):
        return {
            "hours": self.hours,
            "confidence": self.confidence,
            "method": self.method,
        }


class Estimator:
    """Base strategy. ``estimate`` returns a [PowerOnHoursEstimate] or None."""

    id = ""

    def estimate(self, signals):
        raise NotImplementedError


class BatteryCycleEstimator(Estimator):
    """Battery charge cycles are the closest analog to wear we can read
    without root (Android 14+ exposes BATTERY_PROPERTY_CYCLE_COUNT)."""

    id = "battery_cycle"
    HOURS_PER_CYCLE = 18  # ~ a day of being powered on per full charge cycle

    def estimate(self, signals):
        cycles = signals.get("battery_cycle_count")
        if not cycles:
            return None
        return PowerOnHoursEstimate(
            cycles * self.HOURS_PER_CYCLE, CONFIDENCE_MEDIUM, self.id
        )


class BootCountEstimator(Estimator):
    """Settings.Global.BOOT_COUNT (API 24+, no permission) counts reboots.
    Times an average uptime-per-boot gives a coarse lower bound."""

    id = "boot_count"
    HOURS_PER_BOOT = 24

    def estimate(self, signals):
        boots = signals.get("boot_count")
        if not boots:
            return None
        return PowerOnHoursEstimate(
            boots * self.HOURS_PER_BOOT, CONFIDENCE_LOW, self.id
        )


class DeviceAgeEstimator(Estimator):
    """Calendar age (from first system-app install / build date) times a duty
    cycle. Weakest signal, but almost always available."""

    id = "device_age"
    DUTY_CYCLE = 0.30  # fraction of calendar time the device is powered on

    def estimate(self, signals):
        age_days = signals.get("device_age_days")
        if not age_days:
            return None
        return PowerOnHoursEstimate(
            age_days * 24 * self.DUTY_CYCLE, CONFIDENCE_LOW, self.id
        )


# Ordered by descending confidence: the first strategy with a usable signal wins.
ESTIMATORS = [
    BatteryCycleEstimator(),
    BootCountEstimator(),
    DeviceAgeEstimator(),
]


def estimate_power_on_hours(signals):
    """Return the best available [PowerOnHoursEstimate], or None if no signal."""
    if not signals:
        return None
    for estimator in ESTIMATORS:
        result = estimator.estimate(signals)
        if result is not None:
            return result
    return None


# --- Swappable estimator implementations ------------------------------------
#
# The strategies above are one way to turn signals into hours. The estimator
# is expected to change often while real devices teach us which signals are
# reliable, so the implementation in use is picked by name
# (settings.MOBILE_POH_ESTIMATOR) from a registry. A new implementation:
#
#     @register_poh_estimator("battery_capacity_v1")
#     class BatteryCapacityEstimator(PohEstimator):
#         def estimate(self, data):
#             signals = data.get("signals") or {}
#             ...
#
# Implementations receive the whole snapshot ``data`` block (``usage``,
# ``signals``, ``system_properties``, ``android``...), not just ``usage``, so
# they can use any signal the app collected. Stored evidences keep every raw
# signal: after switching implementation, ``manage.py reestimate_mobile_poh``
# recomputes the products already registered.

DEFAULT_POH_ESTIMATOR = "usage_chain_v1"

_POH_ESTIMATORS = {}


class PohEstimator:
    """A named power-on hours estimator over a whole snapshot ``data`` block."""

    name = ""

    def estimate(self, data):
        """Return a [PowerOnHoursEstimate], or None when it has nothing to go on."""
        raise NotImplementedError


def register_poh_estimator(name):
    """Class decorator: make an implementation selectable by ``name``."""

    def decorator(cls):
        cls.name = name
        _POH_ESTIMATORS[name] = cls
        return cls

    return decorator


def available_poh_estimators():
    return sorted(_POH_ESTIMATORS)


def get_poh_estimator(name=None):
    """Factory: the estimator called ``name``, or the one configured in settings."""
    if name is None:
        from django.conf import settings

        name = getattr(settings, "MOBILE_POH_ESTIMATOR", DEFAULT_POH_ESTIMATOR)
    try:
        return _POH_ESTIMATORS[name]()
    except KeyError:
        raise ValueError(
            "Unknown power-on hours estimator {!r}. Available: {}".format(
                name, ", ".join(available_poh_estimators())
            )
        )


def estimate_mobile_power_on_hours(data, estimator=None):
    """Estimate power-on hours of a workbench-android snapshot ``data`` block
    with the configured implementation (or ``estimator``)."""
    if not data:
        return None
    return (estimator or get_poh_estimator()).estimate(data)


@register_poh_estimator(DEFAULT_POH_ESTIMATOR)
class UsageChainEstimator(PohEstimator):
    """First usable strategy of ESTIMATORS over the ``usage`` block."""

    def estimate(self, data):
        return estimate_power_on_hours(data.get("usage") or {})
