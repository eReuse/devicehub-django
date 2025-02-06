import json
import hashlib
import logging

from evidence import legacy_parse
from evidence import old_parse
from evidence import normal_parse
from evidence.parse_details import ParseSnapshot

from evidence.models import SystemProperty
from evidence.xapian import index
from evidence.normal_parse_details import get_inxi_key, get_inxi
from django.conf import settings

if settings.DPP:
    from dpp.api_dlt import register_device_dlt, register_passport_dlt

logger = logging.getLogger('django')


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

        We have 4 cases for parser diferents snapshots than come from workbench.
        1) worbench 11 is old_parse.
        2) legacy is the worbench-script when create a snapshot for devicehub-teal
        3) some snapshots come as a credential. In this case is parsed as normal_parse
        4) normal snapshot from worbench-script is the most basic and is parsed as normal_parse
        """
        self.evidence = evidence_json.copy()
        self.uuid = self.evidence.get('uuid')
        self.user = user

        if evidence_json.get("credentialSubject"):
            self.build = normal_parse.Build(evidence_json)
            self.uuid = evidence_json.get("credentialSubject", {}).get("uuid")
        elif evidence_json.get("software") != "workbench-script":
            self.build = old_parse.Build(evidence_json)
        elif evidence_json.get("data",{}).get("lshw"):
            self.build = legacy_parse.Build(evidence_json)
        else:
            self.build = normal_parse.Build(evidence_json)

        if check:
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
            SystemProperty.objects.create(
                uuid=self.uuid,
                owner=self.user.institution,
                user=self.user,
                key=k,
                value=self.sign(v)
            )

    def sign(self, doc):
        return hashlib.sha3_256(doc.encode()).hexdigest()

    def register_device_dlt(self):
        legacy_dpp = self.build.algorithms.get('ereuse22')
        chid = self.sign(legacy_dpp)
        phid = self.sign(json.dumps(self.build.get_doc()))
        register_device_dlt(chid, phid, self.uuid, self.user)
        register_passport_dlt(chid, phid, self.uuid, self.user)
