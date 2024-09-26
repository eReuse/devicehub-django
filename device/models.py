from django.db import models

from utils.constants import STR_SM_SIZE, STR_SIZE, STR_EXTEND_SIZE, ALGOS
from evidence.models import Annotation, Evidence
from user.models import User
from lot.models import DeviceLot


class Device:
    class Types(models.TextChoices):
        DESKTOP = "Desktop"
        LAPTOP = "Laptop"
        SERVER = "Server"
        GRAPHICCARD = "GraphicCard"
        HARDDRIVE = "HardDrive"
        SOLIDSTATEDRIVE = "SolidStateDrive"
        MOTHERBOARD = "Motherboard"
        NETWORKADAPTER = "NetworkAdapter"
        PROCESSOR = "Processor"
        RAMMODULE = "RamModule"
        SOUNDCARD = "SoundCard"
        DISPLAY = "Display"
        BATTERY = "Battery"
        CAMERA = "Camera"

    def __init__(self, *args, **kwargs):
        # the id is the chid of the device
        self.id = kwargs["id"]
        self.pk = self.id
        self.shortid = self.pk[:6]
        self.algorithm = None
        self.owner = None
        self.annotations =  []
        self.hids = []
        self.uuids = []
        self.evidences = []
        self.lots = []
        self.last_evidence = None
        self.get_last_evidence()

    def initial(self):
        self.get_annotations()
        self.get_uuids()
        self.get_hids()
        self.get_evidences()
        self.get_lots()

    def get_annotations(self):
        if self.annotations:
            return self.annotations

        self.annotations = Annotation.objects.filter(
            type=Annotation.Type.SYSTEM,
            value=self.id
        ).order_by("-created")

        if self.annotations.count():
            self.algorithm = self.annotations[0].key
            self.owner = self.annotations[0].owner

        return self.annotations

    def get_user_annotations(self):
        if not self.uuids:
            self.get_uuids()

        annotations = Annotation.objects.filter(
            uuid__in=self.uuids,
            owner=self.owner,
            type=Annotation.Type.USER
        )
        return annotations

    def get_user_documents(self):
        if not self.uuids:
            self.get_uuids()

        annotations = Annotation.objects.filter(
            uuid__in=self.uuids,
            owner=self.owner,
            type=Annotation.Type.DOCUMENT
        )
        return annotations

    def get_uuids(self):
        for a in self.get_annotations():
            if a.uuid not in self.uuids:
                self.uuids.append(a.uuid)

    def get_hids(self):
        annotations = self.get_annotations()

        self.hids = list(set(annotations.filter(
            type=Annotation.Type.SYSTEM,
            key__in=ALGOS.keys(),
        ).values_list("value", flat=True)))

    def get_evidences(self):
        if not self.uuids:
            self.get_uuids()

        self.evidences = [Evidence(u) for u in self.uuids]

    def get_last_evidence(self):
        annotations = self.get_annotations()
        if not annotations.count():
            return
        annotation = annotations.first()
        self.last_evidence = Evidence(annotation.uuid)

    def last_uuid(self):
        return self.uuids[0]

    def get_lots(self):
        self.lots = [x.lot for x in DeviceLot.objects.filter(device_id=self.id)]

    @classmethod
    def get_unassigned(cls, institution):
        chids = DeviceLot.objects.filter(lot__owner=institution).values_list("device_id", flat=True).distinct()
        annotations = Annotation.objects.filter(
            owner=institution,
            type=Annotation.Type.SYSTEM,
        ).exclude(value__in=chids).values_list("value", flat=True).distinct()
        return [cls(id=x) for x in annotations]

        # return cls.objects.filter(
        #     owner=user
        #     ).annotate(num_lots=models.Count('lot')).filter(num_lots=0)

    @property
    def is_websnapshot(self):
        if not self.last_evidence:
            self.get_last_evidence()
        return self.last_evidence.doc['type'] == "WebSnapshot"

    @property
    def last_user_evidence(self):
        if not self.last_evidence:
            self.get_last_evidence()
        return self.last_evidence.doc['kv'].items()

    @property
    def manufacturer(self):
        if not self.last_evidence:
            self.get_last_evidence()
        return self.last_evidence.get_manufacturer()

    @property
    def type(self):
        if self.last_evidence.doc['type'] == "WebSnapshot":
            return self.last_evidence.doc.get("device", {}).get("type", "")

        if not self.last_evidence:
            self.get_last_evidence()
        return self.last_evidence.get_chassis()

    @property
    def model(self):
        if not self.last_evidence:
            self.get_last_evidence()
        return self.last_evidence.get_model()

    @property
    def components(self):
        if not self.last_evidence:
            self.get_last_evidence()
        return self.last_evidence.get_components()
