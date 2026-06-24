import copy
import json
import hashlib
import logging

from evidence import legacy_parse
from evidence import old_parse
from evidence import normal_parse
from evidence import universal_parse
from evidence.sources import Sources, detect, WB11, LEGACY, INXI, DMI

from evidence.models import SystemProperty
from evidence.xapian import index
from evidence.normal_parse_details import get_inxi_key, get_inxi
from utils.constants import ALGO_EREUSE22
from django.conf import settings

if settings.DPP:
    from dpp.api_dlt import register_device_dlt, register_passport_dlt

logger = logging.getLogger('django')

BUILDERS = {
    WB11: old_parse.Build,
    LEGACY: legacy_parse.Build,
    INXI: normal_parse.Build,
    DMI: universal_parse.Build,
}


def get_mac(inxi):
    nets = get_inxi_key(inxi, "Network")
    networks = [(nets[i], nets[i + 1]) for i in range(0, len(nets) - 1, 2)]

    for n, iface in networks:
        if get_inxi(n, "port"):
            return get_inxi(iface, 'mac')


class Build:
    def __init__(self, evidence_json, user, check=False):
        """
        This Build do the save in xapian as document, in Annotations and do
        register in dlt if is configured for that.

        We have 5 cases for parser diferents snapshots than come from workbench.
        1) worbench 11 is old_parse.
        2) legacy is the worbench-script when create a snapshot for devicehub-teal
        3) some snapshots come as a credential. In this case is parsed as normal_parse
        4) normal snapshot from worbench-script is the most basic and is parsed as normal_parse
        5) workbench-script snapshot without inxi (e.g. Windows): universal_parse (dmidecode + smartctl)
        """
        self.evidence = copy.deepcopy(evidence_json)
        self.user = user

        self.sources = Sources(self.evidence)
        self.uuid = self.sources.uuid
        builder = BUILDERS.get(detect(self.sources), normal_parse.Build)
        self.build = builder(self.sources.snapshot)

        if check:
            return

        if not self.build.uuid:
            return

        self.index()
        self.create_annotations()
        if settings.DPP:
            self.register_device_dlt()

    def index(self):
        snap = json.dumps(self.evidence)
        index(self.user.institution, self.uuid, snap)

    def create_annotations(self):
        prop = SystemProperty.objects.filter(
                uuid=self.uuid,
                owner=self.user.institution,
        )

        if prop:
            txt = "Warning: Snapshot %s already registered (annotation exists)"
            logger.warning(txt, self.uuid)
            return

        for k, v in self.build.algorithms.items():
            value = "{}:{}".format(k, self.sign(v))
            SystemProperty.objects.create(
                uuid=self.uuid,
                owner=self.user.institution,
                user=self.user,
                key=k,
                value=value
            )

    def sign(self, doc):
        return hashlib.sha3_256(doc.encode()).hexdigest()

    def register_device_dlt(self):
        legacy_dpp = self.build.algorithms.get(ALGO_EREUSE22)
        chid = self.sign(legacy_dpp)
        phid = self.sign(json.dumps(self.build.get_doc()))
        register_device_dlt(chid, phid, self.uuid, self.user)
        register_passport_dlt(chid, phid, self.uuid, self.user)
