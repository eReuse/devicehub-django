import json

from dmidecode import DMIParse
from django.db import models

from utils.constants import STR_SM_SIZE, STR_EXTEND_SIZE, CHASSIS_DH
from evidence.xapian import search
from user.models import User, Institution


class Annotation(models.Model):
    class Type(models.IntegerChoices):
        SYSTEM= 0, "System"
        USER = 1, "User"
        DOCUMENT = 2, "Document"

    created = models.DateTimeField(auto_now_add=True)
    uuid = models.UUIDField()
    owner = models.ForeignKey(Institution, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    type =  models.SmallIntegerField(choices=Type)
    key = models.CharField(max_length=STR_EXTEND_SIZE)
    value = models.CharField(max_length=STR_EXTEND_SIZE)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["type", "key", "uuid"], name="unique_type_key_uuid")
        ]


class Evidence:
    def __init__(self, uuid):
        self.uuid = uuid
        self.owner = None
        self.doc = None
        self.created = None
        self.dmi = None
        self.annotations =  []

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

    def get_doc(self):
        self.doc = {}
        if not self.owner:
            self.get_owner()
        qry = 'uuid:"{}"'.format(self.uuid)
        matches = search(self.owner, qry, limit=1)
        if matches.size() < 0:
            return

        for xa in matches:
            self.doc = json.loads(xa.document.get_data())
            
        if self.doc.get("software") == "EreuseWorkbench":
            dmidecode_raw = self.doc["data"]["dmidecode"]
            self.dmi = DMIParse(dmidecode_raw)


    def get_time(self):
        if not self.doc:
            self.get_doc()
        self.created = self.doc.get("endTime")

        if not self.created:
            self.created = self.annotations.last().created

    def components(self):
        return self.doc.get('components', [])

    def get_manufacturer(self):
        if self.doc.get("software") != "EreuseWorkbench":
            return self.doc['device']['manufacturer']
        
        return self.dmi.manufacturer().strip()
    
    def get_model(self):
        if self.doc.get("software") != "EreuseWorkbench":
            return self.doc['device']['model']
        
        return self.dmi.model().strip()

    def get_chassis(self):
        if self.doc.get("software") != "EreuseWorkbench":
            return self.doc['device']['model']
        
        chassis = self.dmi.get("Chassis")[0].get("Type", '_virtual')        
        lower_type = chassis.lower()
        
        for k, v in CHASSIS_DH.items():
            if lower_type in v:
                return k
        return ""



    @classmethod
    def get_all(cls, user):
        return Annotation.objects.filter(
            owner=user.institution,
            type=Annotation.Type.SYSTEM,
        ).order_by("-created").values_list("uuid", flat=True).distinct()