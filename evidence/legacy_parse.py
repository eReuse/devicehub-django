import json
import logging

from dmidecode import DMIParse
from json_repair import repair_json
from evidence.mixin_parse import BuildMix
from evidence.legacy_parse_details import get_lshw_child, ParseSnapshot
from utils.constants import CHASSIS_DH


logger = logging.getLogger('django')


def get_mac(lshw):
    try:
        if type(lshw) is dict:
            hw = lshw
        else:
            hw = json.loads(lshw)
    except json.decoder.JSONDecodeError:
        hw = json.loads(repair_json(lshw))

    nets = []
    get_lshw_child(hw, nets, 'network')

    nets_sorted = sorted(nets, key=lambda x: x['businfo'])

    if nets_sorted:
        mac = nets_sorted[0]['serial']
        logger.debug("The snapshot has the following MAC: %s" , mac)
        return mac


class Build(BuildMix):
    # This parse is for get info from snapshots created with
    # workbench-script but builded for send to devicehub-teal

    def get_details(self):
        dmidecode_raw = self.json["data"]["dmidecode"]
        self.dmi = DMIParse(dmidecode_raw)

        self.manufacturer = self.dmi.manufacturer().strip()
        self.model = self.dmi.model().strip()
        self.chassis = self.get_chassis_dh()
        self.serial_number = self.dmi.serial_number()
        self.sku = self.get_sku()
        self.typ = self.chassis
        self.version = self.get_version()

    def get_chassis_dh(self):
        chassis = self.get_chassis()
        lower_type = chassis.lower()
        for k, v in CHASSIS_DH.items():
            if lower_type in v:
                return k
        return self.default

    def get_sku(self):
        return self.dmi.get("System")[0].get("SKU Number", "n/a").strip()

    def get_chassis(self):
        return self.dmi.get("Chassis")[0].get("Type", '_virtual') #

    def get_version(self):
        return self.dmi.get("System")[0].get("Verson", '_virtual')

    def _get_components(self):
        data = ParseSnapshot(self.json)
        self.components = data.components
