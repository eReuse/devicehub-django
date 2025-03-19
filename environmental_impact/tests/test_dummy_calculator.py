import unittest
from unittest.mock import Mock, patch
from environmental_impact.algorithms.dummy_algo.dummy_calculator import (
    DummyEnvironmentalImpactAlgorithm,
)
from device.models import Device
from environmental_impact.models import EnvironmentalImpact


class DummyEnvironmentalImpactAlgorithmTests(unittest.TestCase):

    def setUp(self):
        self.algorithm = DummyEnvironmentalImpactAlgorithm()
        self.device = Mock(spec=Device)
        self.device.last_evidence = Mock()
        self.device.last_evidence.inxi = True
        self.device.components = [
            {
                "type": "Motherboard",
                "manufacturer": "TOSHIBA",
                "model": "Portable PC",
                "serialNumber": "C0BZ6MN2",
                "version": "Version A0",
                "biosDate": "11/09/2011",
                "biosVersion": "1.40",
                "slots": 2,
                "ramSlots": "",
                "ramMaxSize": "10 GiB",
            },
            {
                "type": "Processor",
                "model": "0x2A (42)",
                "arch": "Sandy Bridge",
                "bits": 64,
                "gen": "core 2",
                "family": "6",
                "date": "2010-12",
                "L1": "128 KiB",
                "L2": "512 KiB",
                "L3": "3 MiB",
                "cpus": "1",
                "cores": 2,
                "threads": 4,
                "bogomips": 12769,
                "base/boost": "1600/3600",
                "min/max": "800/2300",
                "ext-clock": "100 MHz",
                "volts": "1.3 V",
            },
            {
                "type": "RamModule",
                "manufacturer": "802C",
                "model": "8KTF51264HZ-1G9P1",
                "serialNumber": "12A1582B",
                "speed": "1333 MT/s",
                "bits": "64",
                "interface": "DDR3",
            },
            {
                "type": "GraphicCard",
                "memory": "n/a",
                "manufacturer": "Toshiba",
                "model": "Intel 2nd Generation Core Processor Family Integrated Graphics",
                "arch": "Gen-6",
                "serialNumber": "",
                "integrated": False,
            },
            {
                "type": "Display",
                "model": "",
                "manufacturer": "",
                "serialNumber": "",
                "size": "N/A in console",
                "diagonal": "",
                "resolution": "",
                "date": "",
                "ratio": "",
            },
            {
                "type": "NetworkAdapter",
                "model": "Intel 82579V Gigabit Network",
                "manufacturer": "",
                "serialNumber": "e8:e0:b7:c8:66:51",
                "speed": "100 Mbps",
                "interface": "Integrated",
            },
            {
                "type": "SoundCard",
                "model": "Intel 6 Series/C200 Series Family High Definition Audio",
                "manufacturer": "Toshiba 6",
                "serialNumber": "",
            },
            {
                "type": "Storage",
                "manufacturer": "Toshiba",
                "model": "THNSNB128GMCJ",
                "serialNumber": "Y1LS11Z6TTEZ",
                "size": "119.24 GiB",
                "speed": "3.0 Gb/s",
                "interface": "",
                "firmware": "",
                "sata": "2.6",
                "cycles": "7291",
                "health": "PASSED",
                "time of used": "245d 7h",
                "read used": "",
                "written used": "",
            },
            {
                "type": "Battery",
                "model": "G71C000CH310",
                "serialNumber": "0000000942",
                "condition": "0.3/46.5 Wh (0.6%)",
                "cycles": "",
                "volts": "15.1",
            },
        ]

    def test_get_power_on_hours_from_inxi_device(self):
        hours = self.algorithm.get_power_on_hours_from(self.device)
        self.assertEqual(hours, 5887)  # 245 days + 7 hours in hours

    def test_convert_str_time_to_hours(self):
        result = self.algorithm.convert_str_time_to_hours("1y 2d 3h", False)
        self.assertEqual(
            result,
            8760 + 48 + 3,
            "String to hours conversion should match expected output",
        )

    @patch(
        "environmental_impact.algorithms.dummy_algo.dummy_calculator.render_docs",
        return_value="Dummy Docs",
    )
    def test_environmental_impact_calculation(self, mock_render_docs):
        impact = self.algorithm.get_device_environmental_impact(self.device)
        self.assertIsInstance(
            impact,
            EnvironmentalImpact,
            "Output should be an EnvironmentalImpact instance",
        )
        expected_co2 = 5887 * 40 * 0.475 / 1000
        self.assertAlmostEqual(
            impact.co2_emissions,
            expected_co2,
            2,
            "CO2 emissions calculation should be accurate",
        )
        self.assertEqual(impact.docs, "Dummy Docs", "Docs should be rendered correctly")
