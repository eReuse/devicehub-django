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


class Property(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    owner = models.ForeignKey(Institution, on_delete=models.CASCADE)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True)
    key = models.CharField(max_length=STR_EXTEND_SIZE)
    value = models.CharField(max_length=STR_EXTEND_SIZE)

    class Meta:
        #Only for shared behaviour, it is not a table
        abstract = True


class SystemProperty(Property):
    uuid = models.UUIDField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["key", "uuid"], name="system_unique_type_key_uuid")
        ]

    @property
    def shortid(self):
        return self.value.split(":")[1][:6].upper()

    @property
    def hid(self):
        return self.value.split(":")[1]


class UserProperty(Property):

    class Type(models.IntegerChoices):
        USER = 1, "User"
        ERASE_SERVER = 2, "EraseServer"

    uuid = models.UUIDField()
    type = models.SmallIntegerField(choices=Type, default=Type.USER)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["key", "uuid"], name="userproperty_unique_type_key_uuid")
        ]


class RootAlias(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    owner = models.ForeignKey(Institution, on_delete=models.CASCADE)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True)
    alias = models.CharField(max_length=STR_EXTEND_SIZE)
    root = models.CharField(max_length=STR_EXTEND_SIZE)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "alias"], name="rootalias_unique")
        ]

    @property
    def root_hid(self):
        return self.root.split(":")[1]


class Evidence:
    def __init__(self, uuid):
        self.uuid = uuid
        self.uploaded_by = None
        self.owner = None
        self.doc = None
        self.created = None
        self.dmi = None
        self.inxi = None
        self.properties = []
        self.components = []
        self.default = "n/a"

        self.get_owner()
        self.get_time()

    def get_properties(self):
        # TODO is good not filter by institution?
        self.properties = SystemProperty.objects.filter(
            uuid=self.uuid
        ).order_by("created")

    def get_owner(self):
        if not self.properties:
            self.get_properties()
        a = self.properties.first()
        if a:
            self.owner = a.owner
            self.uploaded_by = a.user

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

        if self.is_beta():
            parse = ParseSnapshot(self.doc)
            device = parse.device
            if not device:
                return
            self.device_manufacturer = device.get("manufacturer") or ''
            self.device_model = device.get("model") or ''
            self.device_serial_number = device.get("serialNumber") or ''
            self.device_chassis = device.get("chassis") or ''
            self.device_version = device.get("version") or ''
            self.components = parse.components

        if self.is_legacy():
            return

        if self.doc.get("credentialSubject"):
            for ev in self.doc["evidence"]:
                if "dmidecode" == ev.get("operation"):
                    dmidecode_raw = ev["output"]
                    if dmidecode_raw:
                        self.dmi = DMIParse(dmidecode_raw)
                if "inxi" == ev.get("operation"):
                    self.inxi = ev["output"]
                    if isinstance(ev["output"], str):
                        self.inxi = json.loads(ev["output"])
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
                if isinstance(self.inxi, str):
                    self.inxi = json.loads(self.inxi)
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
            self.created = self.get_time_created()

    def get_time_created(self):
        return self.properties.last().created.isoformat()

    def get_components(self):
        if self.is_beta():
            return self.components

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

        if self.inxi or self.is_beta():
            return self.device_manufacturer

        if self.is_legacy():
            return self.doc.get('device', {}).get('manufacturer', '')

        try:
            return self.dmi.manufacturer().strip()
        except Exception:
            return ''

    def get_model(self):
        if self.is_web_snapshot():
            kv = self.doc.get('kv', {})
            if len(kv) < 2:
                return ""
            return list(self.doc.get('kv').values())[1]

        if self.inxi or self.is_beta():
            return self.device_model

        if self.is_legacy():
            model = self.doc.get('device', {}).get('model', '') or ''
            version = self.doc.get('device', {}).get('version', '') or ''
            return "{} {}".format(model, version)

        try:
            return self.dmi.model().strip()
        except Exception:
            return ''

    def get_chassis(self):
        if self.inxi or self.is_beta():
            return self.device_chassis

        if self.is_legacy():
            return self.doc.get('device', {}).get('chassis', '')

        dmi_chassis = self.dmi.get("Chassis")
        if not dmi_chassis:
            return ""

        chassis = dmi_chassis[0].get("Type", '_virtual')
        lower_type = chassis.lower()

        for k, v in CHASSIS_DH.items():
            if lower_type in v:
                return k
        return ""

    def get_serial_number(self):
        if self.inxi or self.is_beta():
            return self.device_serial_number

        if self.is_legacy():
            return self.doc.get('device', {}).get('serialNumber', '')

        try:
            return self.dmi.serial_number().strip()
        except Exception:
            return ''

    def get_version(self):
        if self.inxi or self.is_beta():
            return self.device_version

        return ""

    def get_alias(self):
        aliases = [ x.value for x in self.properties ]
        alias_obj = RootAlias.objects.filter(
            alias__in = aliases,
        ).order_by("-created")

        if alias_obj:
            return alias_obj[0].root
        else:
            return self.properties[0].value

    @classmethod
    def get_all(cls, user):
        return SystemProperty.objects.filter(
            owner=user.institution,
        ).order_by("-created").distinct()

    @classmethod
    def get_user_evidences(cls, user):
        return SystemProperty.objects.filter(
            owner=user.institution,
            user=user
        ).order_by("-created").distinct()

    @classmethod
    def get_device_evidences(cls, user, uuids):
        return SystemProperty.objects.filter(
            owner=user.institution,
            uuid__in=uuids
        ).order_by("-created").distinct()

    def set_components(self):
        self.components = ParseSnapshot(self.doc).components

    def is_beta(self):
        return self.doc.get("version") == '2022.12.2-beta'

    def is_legacy(self):
        if self.doc.get("credentialSubject"):
            return False

        return self.doc.get("software") != "workbench-script"

    def is_web_snapshot(self):
        return self.doc.get("type") == "WebSnapshot"

    def is_photo_evidence(self):
        return self.doc.get("type") == "photo25"

    def did_document(self):
        if not self.doc.get("credentialSubject"):
            return ''
        did = self.doc.get('issuer').get('id')
        if "did:web" not in did:
            return ''

        return  "https://{}/did.json".format(
            did.split("did:web:")[1].replace(":", "/")
        )
