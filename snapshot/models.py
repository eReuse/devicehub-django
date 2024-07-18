import json

from django.db import models

from utils.constants import STR_SM_SIZE, STR_EXTEND_SIZE
from snapshot.xapian import search
from user.models import User


class Snapshot:
    def __init__(self, uuid):
        self.uuid = uuid
        self.owner = None
        self.doc = None
        self.created = None
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
        qry = 'uuid:"{}"'.format(self.uuid)
        matches = search(qry, limit=1)
        if matches.size() < 0:
            return

        for xa in matches:
            self.doc = json.loads(xa.document.get_data())

    def get_time(self):
        if not self.doc:
            self.get_doc()
        self.created = self.doc.get("endTime")

        if not self.created:
            self.created = self.annotations.last().created

    def components(self):
        return self.doc.get('components', [])


class Annotation(models.Model):
    class Type(models.IntegerChoices):
        SYSTEM= 0, "System"
        USER = 1, "User"

    created = models.DateTimeField(auto_now_add=True)
    uuid = models.UUIDField()
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    type =  models.SmallIntegerField(choices=Type) 
    key = models.CharField(max_length=STR_EXTEND_SIZE)
    value = models.CharField(max_length=STR_EXTEND_SIZE)
    device = models.ForeignKey('device.Device', on_delete=models.CASCADE)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["type", "key", "uuid"], name="unique_type_key_uuid")
        ]

    def is_user_annotation(self):
        if self.type == self.Type.USER:
            return True
        return False
