from device.models import Device
from unittest.mock import MagicMock


class TestDevice(Device):
    """A test subclass of Device that overrides the database-dependent methods"""
    # TODO Leaving commented bc not used, but might be useful at some  point
    # def get_annotations(self):
    #     """Return empty list instead of querying database"""
    #     return []

    # def get_uuids(self):
    #     """Set uuids directly instead of querying"""
    #     self.uuids = ['uuid1', 'uuid2']

    # def get_hids(self):
    #     """Set hids directly instead of querying"""
    #     self.hids = ['hid1', 'hid2']

    # def get_evidences(self):
    #     """Set evidences directly instead of querying"""
    #     self.evidences = []

    # def get_lots(self):
    #     """Set lots directly instead of querying"""
    #     self.lots = []

    def get_last_evidence(self):
        if not hasattr(self, '_evidence'):
            self._evidence = MagicMock()
            self._evidence.doc = {
                'type': 'Computer',
                'manufacturer': 'Test Manufacturer',
                'model': 'Test Model',
                'device': {
                    'serialNumber': 'SN123456',
                    'type': 'Computer'
                }
            }
            self._evidence.get_manufacturer = lambda: 'Test Manufacturer'
            self._evidence.get_model = lambda: 'Test Model'
            self._evidence.get_chassis = lambda: 'Computer'
            self._evidence.get_components = lambda: [
                {
                    'type': 'CPU',
                    'model': 'Intel i7',
                    'manufacturer': 'Intel'
                },
                {
                    'type': 'RAM',
                    'size': '8GB',
                    'manufacturer': 'Kingston'
                }
            ]
        self.last_evidence = self._evidence


class TestWebSnapshotDevice(TestDevice):
    """A test subclass of Device that simulates a WebSnapshot device"""

    def get_last_evidence(self):
        if not hasattr(self, '_evidence'):
            self._evidence = MagicMock()
            self._evidence.doc = {
                'type': 'WebSnapshot',
                'kv': {
                    'URL': 'http://example.com',
                    'Title': 'Test Page',
                    'Timestamp': '2024-01-01'
                },
                'device': {
                    'type': 'Laptop'
                }
            }
        self.last_evidence = self._evidence
        return self._evidence
