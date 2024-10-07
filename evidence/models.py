import json

from django.db import models

from utils.constants import STR_SM_SIZE, STR_EXTEND_SIZE
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

    def get_time(self):
        if not self.doc:
            self.get_doc()
        self.created = self.doc.get("endTime")

        if not self.created:
            self.created = self.annotations.last().created

    def components(self):
        return self.doc.get('components', [])

    @classmethod
    def get_all(cls, user):
        return Annotation.objects.filter(
            owner=user.institution,
            type=Annotation.Type.SYSTEM,
        ).order_by("-created").values_list("uuid", flat=True).distinct()
