import json
import hashlib

from dmidecode import DMIParse
from django.db import models


from django.db.models import Q
from utils.constants import STR_EXTEND_SIZE, CHASSIS_DH
from evidence.xapian import search
from evidence.parse_details import ParseSnapshot
from evidence.normal_parse_details import get_inxi, get_inxi_key
from user.models import User, Institution

#TODO: base class is abstract; revise if should be for query efficiency
class Property(models.Model):
    class Type(models.IntegerChoices):
        SYSTEM = 0, "System"
        USER = 1, "User"
        DOCUMENT = 2, "Document"
        ERASE_SERVER = 3, "EraseServer"

    created = models.DateTimeField(auto_now_add=True)
    uuid = models.UUIDField()
    owner = models.ForeignKey(Institution, on_delete=models.CASCADE)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True)
    type = models.SmallIntegerField(choices=Type)
    key = models.CharField(max_length=STR_EXTEND_SIZE)
    value = models.CharField(max_length=STR_EXTEND_SIZE)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["type", "key", "uuid"], name="unique_type_key_uuid")
        ]
        abstract = True

class SystemProperty(Property):

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=~Q(type=1), #Enforce that type is not User
                name='property_cannot_be_user'
            ),
        ]

class UserProperty(Property):

    type = models.SmallIntegerField(default=Property.Type.USER)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=Q(type=1), #Enforce that type is User
                name='property_needs_to_be_user'
            ),
        ]



class Evidence:
    def __init__(self, uuid):
        self.uuid = uuid
        self.owner = None
        self.doc = None
        self.created = None
        self.dmi = None
        self.inxi = None
        self.annotations = []
        self.components = []
        self.default = "n/a"

        self.get_owner()
        self.get_time()

    def get_annotations(self):
        self.annotations = Annotation.objects.filter(
            uuid=self.uuid
        ).order_by("created")

    def get_owner(self):
        if not self.annotations:
            self.get_annotations()
        a = self.annotations.first()
        if a:
            self.owner = a.owner

    def get_phid(self):
        if not self.doc:
            self.get_doc()

        return hashlib.sha3_256(json.dumps(self.doc)).hexdigest()

    def get_doc(self):
        self.doc = {}
        self.inxi = None

        if not self.owner:
            self.get_owner()

        qry = 'uuid:"{}"'.format(self.uuid)
        matches = search(self.owner, qry, limit=1)
        if matches and matches.size() < 0:
            return

        for xa in matches:
            self.doc = json.loads(xa.document.get_data())

        if self.is_legacy():
            return

        if self.doc.get("credentialSubject"):
            for ev in self.doc["evidence"]:
                if "dmidecode" == ev.get("operation"):
                    dmidecode_raw = ev["output"]
                if "inxi" == ev.get("operation"):
                    self.inxi = ev["output"]
        else:
            dmidecode_raw = self.doc["data"]["dmidecode"]
            inxi_raw = self.doc.get("data", {}).get("inxi")
            self.dmi = DMIParse(dmidecode_raw)
            try:
                self.inxi = json.loads(inxi_raw)
            except Exception:
                pass
        if self.inxi:
            try:
                machine = get_inxi_key(self.inxi, 'Machine')
                for m in machine:
                    system = get_inxi(m, "System")
                    if system:
                        self.device_manufacturer = system
                        self.device_model = get_inxi(m, "product")
                        self.device_serial_number = get_inxi(m, "serial")
                        self.device_chassis = get_inxi(m, "Type")
                        self.device_version = get_inxi(m, "v")
            except Exception:
                return

    def get_time(self):
        if not self.doc:
            self.get_doc()
        self.created = self.doc.get("endTime")

        if not self.created:
            self.created = self.annotations.last().created

    def get_components(self):
        if self.is_legacy():
            return self.doc.get('components', [])
        self.set_components()
        return self.components

    def get_manufacturer(self):
        if self.is_web_snapshot():
            kv = self.doc.get('kv', {})
            if len(kv) < 1:
                return ""
            return list(self.doc.get('kv').values())[0]

        if self.is_legacy():
            return self.doc.get('device', {}).get('manufacturer', '')

        if self.inxi:
            return self.device_manufacturer

        return self.dmi.manufacturer().strip()

    def get_model(self):
        if self.is_web_snapshot():
            kv = self.doc.get('kv', {})
            if len(kv) < 2:
                return ""
            return list(self.doc.get('kv').values())[1]

        if self.is_legacy():
            return self.doc.get('device', {}).get('model', '')

        if self.inxi:
            return self.device_model

        return self.dmi.model().strip()

    def get_chassis(self):
        if self.is_legacy():
            return self.doc.get('device', {}).get('model', '')

        if self.inxi:
            return self.device_chassis

        chassis = self.dmi.get("Chassis")[0].get("Type", '_virtual')
        lower_type = chassis.lower()

        for k, v in CHASSIS_DH.items():
            if lower_type in v:
                return k
        return ""

    def get_serial_number(self):
        if self.is_legacy():
            return self.doc.get('device', {}).get('serialNumber', '')

        if self.inxi:
            return self.device_serial_number

        return self.dmi.serial_number().strip()

    def get_version(self):
        if self.inxi:
            return self.device_version

        return ""

    @classmethod
    def get_all(cls, user):
        return Annotation.objects.filter(
            owner=user.institution,
            type=Annotation.Type.SYSTEM,
            key="hidalgo1",
        ).order_by("-created").values_list("uuid", "created").distinct()

    def set_components(self):
        self.components = ParseSnapshot(self.doc).components

    def is_legacy(self):
        if self.doc.get("credentialSubject"):
            return False

        return self.doc.get("software") != "workbench-script"

    def is_web_snapshot(self):
        return self.doc.get("type") == "WebSnapshot"

    def did_document(self):
        if not self.doc.get("credentialSubject"):
            return ''
        did = self.doc.get('issuer')
        if not "did:web" in did:
            return ''

        return  "https://{}/did.json".format(
            did.split("did:web:")[1].replace(":", "/")
        )
