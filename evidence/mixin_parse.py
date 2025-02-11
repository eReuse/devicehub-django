import logging
from django.conf import settings

from utils.constants import ALGOS


logger = logging.getLogger('django')


class BuildMix:
    def __init__(self, evidence_json):
        self.json = evidence_json
        self.uuid = self.json.get('uuid')
        self.manufacturer = ""
        self.model = ""
        self.serial_number = ""
        self.chassis = ""
        self.sku = ""
        self.mac = ""
        self.tpy = ""
        self.version = ""
        self.get_details()
        self.generate_chids()

    def get_hid(self, algo):
        algorithm = ALGOS.get(algo, [])
        hid = ""
        for f in algorithm:
            if hasattr(self, f):
                hid += getattr(self, f)
        return hid

    def generate_chids(self):
        self.algorithms = {}
        for k in ALGOS.keys():
            if not settings.DPP and k == 'ereuse22':
                continue

            self.algorithms[k] = self.get_hid(k)


    def get_doc(self):
        self._get_components()
        for c in self.components:
            c.pop("actions", None)

        components = sorted(self.components, key=lambda x: x.get("type"))
        device = self.algorithms.get('ereuse22')

        doc = [("computer", device)]

        for c in components:
            doc.append((c.get("type"), self.get_id_hw_dpp(c)))

        return doc

    def get_id_hw_dpp(self, d):
        algorithm = ALGOS.get("ereuse22", [])
        hid = ""
        for f in algorithm:
            hid += d.get(f, '')
        return hid
