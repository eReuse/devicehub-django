import logging
from django.conf import settings
import hashlib

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
        self.type = ""
        self.version = ""
        self.default = ""
        self.algorithms = {}
        data = self.json.get("data", {})
        if not self.uuid:
            vc_uuid = self.json.get("credentialSubject", {}).get("uuid")
            if not vc_uuid:
                txt = "snapshot without UUID. Software {}".format(
                    self.json.get("software")
                )
                logger.error(txt)
                raise Exception(txt)
            else:
                evidence = self.json.get("evidence", [])
                if len(evidence) < 3:
                    txt = "snapshot without dmidecode and inxi datas"
                    logger.error(txt)
                    raise Exception(txt)

                data["dmidecode"] = evidence[0]
                data["inxi"] = evidence[2]

        dmidecode_raw = data.get("dmidecode")
        inxi_raw = data.get("inxi")
        device = self.json.get("device")
        if not dmidecode_raw and not inxi_raw and not device:
            txt = "snapshot without dmidecode and inxi datas"
            logger.error(txt)
            raise Exception(txt)

        self.get_details()
        self.generate_chids()

    def get_hid(self, algo):
        algorithm = ALGOS.get(algo, [])
        hid = ""
        for f in algorithm:
            if hasattr(self, f):
                hid += getattr(self, f) or ''
        return self.sign(hid)

    def generate_chids(self):
        self.algorithms = {}
        k = settings.DEVICEHUB_ALGORITHM_DEVICE
        if self.type == "Display":
            k = settings.DEVICEHUB_ALGORITHM_DISPLAY
        elif self.type == "Disk":
            k = settings.DEVICEHUB_ALGORITHM_DISK
        elif self.type == "Image":
            k = settings.DEVICEHUB_ALGORITHM_PHOTO
        self.algorithms[k] = self.get_hid(k)
        # for k in ALGOS.keys():
        #     if not settings.DPP and k == 'ereuse22':
        #         continue

        #     self.algorithms[k] = self.get_hid(k)

    def sign(self, doc):
        return hashlib.sha3_256(doc.encode()).hexdigest()

    def get_doc(self):
        self._get_components()

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
