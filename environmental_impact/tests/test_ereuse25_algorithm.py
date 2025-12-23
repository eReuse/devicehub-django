import unittest
from unittest.mock import Mock, patch
from environmental_impact.algorithms.ereuse2025.ereuse2025 import (
    EReuse2025EnvironmentalImpactAlgorithm,
)
from environmental_impact.algorithms.common import get_poh_from_device
from device.models import Device
from environmental_impact.models import EnvironmentalImpact


class EReuse2025AlgorithmTests(unittest.TestCase):
    """
    Test suite for the ereuse25 environmental impact algorithm.

    Tests GHG emissions calculation based on the formula:
    U = FU · (P_idle + P_sleep) = FU · (KWh_idle · Poh + KW_sleep · Ts)
    """

    def setUp(self):
        self.algorithm = EReuse2025EnvironmentalImpactAlgorithm()
        self.device = Mock(spec=Device)

        # Mock evidence with components
        evidence = Mock()
        evidence.uuid = "test-evidence-uuid"
        evidence.inxi = True
        evidence.get_components = Mock(
            return_value=[
                {
                    "type": "Storage",
                    "manufacturer": "Samsung",
                    "model": "SSD 970 EVO Plus 500GB",
                    "serialNumber": "S4EWNX0N123456",
                    "size": "465.76 GiB",
                    "speed": "6.0 Gb/s",
                    "interface": "NVMe",
                    "firmware": "2B2QEXM7",
                    "sata": "",
                    "cycles": "1234",
                    "health": "PASSED",
                    "time of used": "1000d 12h",
                    "read used": "50.5 TB",
                    "written used": "25.2 TB",
                },
            ]
        )

        # Set up device with evidence
        self.device.last_evidence = evidence
        self.device.evidences = [evidence]
        self.device.components = evidence.get_components()

    def test_get_power_on_hours_from_device(self):
        """Test extracting power-on hours from device evidence."""
        hours = get_poh_from_device(self.device)
        self.assertIsInstance(hours, int)
        # Should extract from "time of used": "1000d 12h" = 24012 hours
        self.assertEqual(hours, 24012)

    @patch(
        "environmental_impact.algorithms.common.render_algorithm_docs",
        return_value="Algorithm Docs",
    )
    def test_environmental_impact_calculation_desktop(self, mock_render_docs):
        """Test complete environmental impact calculation for desktop."""
        self.device.type = Device.Types.DESKTOP
        impact = self.algorithm.get_device_environmental_impact(self.device)
        self.assertIsInstance(impact, EnvironmentalImpact)
        self.assertIn("in_use", impact.kg_CO2e)
        self.assertIn("carbon_intensity_factor", impact.kg_CO2e)
        self.assertEqual(impact.constants, self.algorithm.algorithm_constants)
        self.assertEqual(impact.docs, "Algorithm Docs")
        # Verify relevant input data structure includes lifecycle metrics
        expected_keys = {
            "total_usage_time",
            "reuse_time",
            "evidence_count",
            "disk_change_count",
            "hours_in_sleep_mode",
            "carbon_intensity_factor",
            "device_type",
        }
        self.assertEqual(set(impact.relevant_input_data.keys()), expected_keys)

    @patch(
        "environmental_impact.algorithms.common.render_algorithm_docs",
        return_value="Algorithm Docs",
    )
    def test_environmental_impact_calculation_laptop(self, mock_render_docs):
        """Test complete environmental impact calculation for laptop."""
        self.device.type = Device.Types.LAPTOP
        impact = self.algorithm.get_device_environmental_impact(self.device)

        self.assertIsInstance(impact, EnvironmentalImpact)
        self.assertIn("in_use", impact.kg_CO2e)
        self.assertEqual(impact.relevant_input_data["device_type"], Device.Types.LAPTOP)

    def test_compute_energy_consumption_idle_desktop(self):
        """Test idle energy consumption calculation for desktop."""
        power_on_hours = 1000
        device_type = Device.Types.DESKTOP

        result = self.algorithm._compute_energy_consumption_in_kwh_while_idle(
            power_on_hours, device_type
        )

        expected = 1000 * 0.039  # Desktop idle power
        self.assertEqual(result, expected)

    def test_compute_energy_consumption_idle_laptop(self):
        """Test idle energy consumption calculation for laptop."""
        power_on_hours = 800
        device_type = Device.Types.LAPTOP

        result = self.algorithm._compute_energy_consumption_in_kwh_while_idle(
            power_on_hours, device_type
        )

        expected = 800 * 0.016  # Laptop idle power
        self.assertEqual(result, expected)

    def test_compute_energy_consumption_idle_default(self):
        """Test idle energy consumption for other device types."""
        power_on_hours = 500
        device_type = Device.Types.SERVER

        result = self.algorithm._compute_energy_consumption_in_kwh_while_idle(
            power_on_hours, device_type
        )

        expected = 500 * 0.02  # Default idle power
        self.assertEqual(result, expected)

    def test_get_time_while_in_sleep_mode(self):
        """Test sleep time calculation using the formula."""
        power_on_hours = 1000
        result = self.algorithm._get_time_while_in_sleep_mode(power_on_hours)

        # Formula: (0.2562 / (1 - 0.2562)) * 1000 = 344.34 -> 344
        expected = int((0.2562 / (1 - 0.2562)) * power_on_hours)
        self.assertEqual(result, expected)
        self.assertEqual(result, 344)

    def test_get_time_while_in_sleep_mode_zero(self):
        """Test sleep time calculation with zero hours."""
        result = self.algorithm._get_time_while_in_sleep_mode(0)
        self.assertEqual(result, 0)

    def test_compute_energy_consumption_sleeping_desktop(self):
        """Test sleep energy consumption for desktop."""
        power_on_hours = 1000
        device_type = Device.Types.DESKTOP

        result = self.algorithm._compute_energy_consumption_while_sleeping(
            power_on_hours, device_type
        )

        sleep_time = 344  # From previous test
        expected = sleep_time * 0.0016  # Desktop sleep power
        self.assertEqual(result, expected)

    def test_compute_energy_consumption_sleeping_laptop(self):
        """Test sleep energy consumption for laptop."""
        power_on_hours = 800
        device_type = Device.Types.LAPTOP

        result = self.algorithm._compute_energy_consumption_while_sleeping(
            power_on_hours, device_type
        )

        sleep_time = self.algorithm._get_time_while_in_sleep_mode(power_on_hours)
        expected = sleep_time * 0.0005  # Laptop sleep power
        self.assertEqual(result, expected)

    def test_compute_energy_consumption_sleeping_default(self):
        """Test sleep energy consumption for other device types."""
        power_on_hours = 600
        device_type = Device.Types.SERVER

        result = self.algorithm._compute_energy_consumption_while_sleeping(
            power_on_hours, device_type
        )

        sleep_time = self.algorithm._get_time_while_in_sleep_mode(power_on_hours)
        expected = sleep_time * 0.001  # Default sleep power
        self.assertEqual(result, expected)

    def test_algorithm_constants_exist(self):
        """Test that all required algorithm constants are defined."""
        required_constants = {
            "AVG_KWATTS_DESKTOP_IDLE",
            "AVG_KWATTS_LAPTOP_IDLE",
            "AVG_KWATTS_DEFAULT_IDLE",
            "MEAN_PERCENTAGE_DEVICE_IS_SLEEPING",
            "AVG_KWATTS_DESKTOP_SLEEP",
            "AVG_KWATTS_LAPTOP_SLEEP",
            "AVG_KWATTS_DEFAULT_SLEEP",
        }

        actual_constants = set(self.algorithm.algorithm_constants.keys())
        self.assertEqual(actual_constants, required_constants)

    def test_algorithm_constants_values(self):
        """Test that algorithm constants have reasonable values."""
        constants = self.algorithm.algorithm_constants
        # Power values should be positive
        self.assertGreater(constants["AVG_KWATTS_DESKTOP_IDLE"], 0)
        self.assertGreater(constants["AVG_KWATTS_LAPTOP_IDLE"], 0)
        self.assertGreater(constants["AVG_KWATTS_DEFAULT_IDLE"], 0)

        # Sleep percentage should be between 0 and 1
        sleep_pct = constants["MEAN_PERCENTAGE_DEVICE_IS_SLEEPING"]
        self.assertGreaterEqual(sleep_pct, 0)
        self.assertLessEqual(sleep_pct, 1)

    def test_co2_emissions_calculation_with_known_values(self):
        """Test CO2 emissions calculation with known input values."""
        # Using mocked values to test the calculation precisely
        power_on_hours = 1000
        self.device.type = Device.Types.DESKTOP

        # Calculate expected values manually
        idle_energy = power_on_hours * 0.039  # 39 kWh
        sleep_time = int((0.2562 / (1 - 0.2562)) * power_on_hours)  # 344h
        sleep_energy = sleep_time * 0.0016  # 0.5504 kWh
        total_energy = idle_energy + sleep_energy  # 39.5504 kWh

        # Mock to return specific carbon intensity
        with patch(
            "environmental_impact.algorithms.ereuse2025.carbon_intensity."
            "carbon_intensity.get_carbon_intensity_factor_from",
            return_value=250.0,
        ), patch(
            "environmental_impact.algorithms.common.get_poh_from_device",
            return_value=power_on_hours,
        ):
            result = self.algorithm._compute_co2_emissions_while_in_use(self.device)

            expected_co2 = (250.0 * total_energy) / 1000
            self.assertAlmostEqual(result["in_use"], expected_co2, places=4)
            self.assertEqual(result["carbon_intensity_factor"], 250.0)

    @patch(
        "environmental_impact.algorithms.common.render_algorithm_docs",
        return_value="Algorithm Docs",
    )
    def test_get_lot_environmental_impact_empty_list(self, mock_render_docs):
        """Test lot impact calculation with empty device list."""
        devices = []
        impact = self.algorithm.get_lot_environmental_impact(devices)
        self.assertIsInstance(impact, EnvironmentalImpact)
        self.assertEqual(impact.kg_CO2e["in_use"], 0.0)
        self.assertEqual(impact.constants, self.algorithm.algorithm_constants)
        self.assertIn("Algorithm Docs", impact.docs)

    @patch(
        "environmental_impact.algorithms.common.render_algorithm_docs",
        return_value="Algorithm Docs",
    )
    def test_get_lot_environmental_impact_single_device(self, mock_render_docs):
        """Test lot impact calculation with single device."""
        devices = [self.device]
        self.device.type = Device.Types.LAPTOP
        impact = self.algorithm.get_lot_environmental_impact(devices)
        self.assertIsInstance(impact, EnvironmentalImpact)
        self.assertIn("in_use", impact.kg_CO2e)
        self.assertGreater(impact.kg_CO2e["in_use"], 0.0)
        self.assertEqual(impact.constants, self.algorithm.algorithm_constants)

    @patch(
        "environmental_impact.algorithms.common.render_algorithm_docs",
        return_value="Algorithm Docs",
    )
    def test_get_lot_environmental_impact_multiple_devices(self, mock_render_docs):
        """Test lot impact calculation with multiple devices."""
        # Create three mock devices
        device1 = Mock(spec=Device)
        device1.type = Device.Types.DESKTOP
        device1.last_evidence = self.device.last_evidence
        device1.evidences = [self.device.last_evidence]
        device1.components = self.device.components

        device2 = Mock(spec=Device)
        device2.type = Device.Types.LAPTOP
        device2.last_evidence = self.device.last_evidence
        device2.evidences = [self.device.last_evidence]
        device2.components = self.device.components

        device3 = Mock(spec=Device)
        device3.type = Device.Types.SERVER
        device3.last_evidence = self.device.last_evidence
        device3.evidences = [self.device.last_evidence]
        device3.components = self.device.components

        devices = [device1, device2, device3]

        # Get individual impacts for comparison
        impact1 = self.algorithm.get_device_environmental_impact(device1)
        impact2 = self.algorithm.get_device_environmental_impact(device2)
        impact3 = self.algorithm.get_device_environmental_impact(device3)

        # Get lot impact
        lot_impact = self.algorithm.get_lot_environmental_impact(devices)

        # Verify aggregation
        expected_total = (
            impact1.kg_CO2e["in_use"]
            + impact2.kg_CO2e["in_use"]
            + impact3.kg_CO2e["in_use"]
        )

        self.assertAlmostEqual(lot_impact.kg_CO2e["in_use"], expected_total, places=6)

    @patch(
        "environmental_impact.algorithms.common.render_algorithm_docs",
        return_value="Algorithm Docs",
    )
    def test_get_lot_environmental_impact_aggregation_correctness(
        self, mock_render_docs
    ):
        """Test that lot impact correctly sums individual device impacts."""
        # Create devices with known power-on hours
        devices = []
        expected_total = 0.0

        for i in range(5):
            device = Mock(spec=Device)
            device.type = Device.Types.LAPTOP
            device.last_evidence = self.device.last_evidence
            device.evidences = [self.device.last_evidence]
            device.components = self.device.components
            devices.append(device)

            # Calculate expected impact for this device
            device_impact = self.algorithm.get_device_environmental_impact(device)
            expected_total += device_impact.kg_CO2e["in_use"]

        lot_impact = self.algorithm.get_lot_environmental_impact(devices)

        self.assertAlmostEqual(lot_impact.kg_CO2e["in_use"], expected_total, places=6)
