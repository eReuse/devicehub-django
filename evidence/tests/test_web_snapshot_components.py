from django.test import TestCase

from evidence.models import Evidence


class WebSnapshotComponentsTests(TestCase):
    """A web snapshot has no components: its kv holds free-form attributes
    typed by hand, which are product data and not parsed hardware."""

    def evidence(self, kv):
        ev = Evidence.__new__(Evidence)
        ev.doc = {
            "type": "WebSnapshot",
            "uuid": "0c1d2e3f-4a5b-6c7d-8e9f-0a1b2c3d4e5f",
            "WEB_ID": "web25:abc",
            "device": {"type": "Laptop"},
            "kv": kv,
        }
        ev.components = []
        return ev

    def test_get_components_is_a_list(self):
        ev = self.evidence({"cpu": "i5", "ram": "8 GiB"})
        self.assertEqual(ev.get_components(), [])

    def test_get_kv_returns_the_attributes(self):
        ev = self.evidence({"cpu": "i5", "ram": "8 GiB"})
        self.assertEqual(ev.get_kv(), {"cpu": "i5", "ram": "8 GiB"})

    def test_get_kv_without_attributes(self):
        ev = self.evidence({})
        self.assertEqual(ev.get_kv(), {})
        del ev.doc["kv"]
        self.assertEqual(ev.get_kv(), {})

    def test_getters_read_the_attributes(self):
        ev = self.evidence({
            "manufacturer": "Acme",
            "model": "X1",
            "serial": "SN1",
            "cpu_model": "i5",
            "ram_total": "8 GiB",
            "drive": "SSD 500 GB",
        })
        self.assertEqual(ev.get_manufacturer(), "Acme")
        self.assertEqual(ev.get_model(), "X1")
        self.assertEqual(ev.get_serial_number(), "SN1")
        self.assertEqual(ev.get_cpu_model(), "i5")
        self.assertEqual(ev.get_ram_total(), "8 GiB")
        self.assertEqual(ev.get_drive(), "SSD 500 GB")

    def test_getters_without_attributes(self):
        ev = self.evidence({})
        self.assertEqual(ev.get_manufacturer(), "")
        self.assertEqual(ev.get_model(), "")
        self.assertEqual(ev.get_chassis(), "Websnapshot")
