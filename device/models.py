from django.db import models

from utils.constants import STR_SM_SIZE, STR_SIZE, STR_EXTEND_SIZE, ALGOS
from snapshot.models import Annotation, Snapshot
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
        self.algorithm = None
        self.owner = None
        self.annotations =  []
        self.hids = []
        self.uuids = []
        self.snapshots = []
        self.last_snapshot = None
        self.get_last_snapshot()

    def initial(self):
        self.get_annotations()
        self.get_uuids()
        self.get_hids()
        self.get_snapshots()
        
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
            
    def get_uuids(self):
        for a in self.get_annotations():
            if not a.uuid in self.uuids:
                self.uuids.append(a.uuid)

    def get_hids(self):
        annotations = self.get_annotations()

        self.hids = annotations.filter(
            type=Annotation.Type.SYSTEM,
            key__in=ALGOS.keys(),
        ).values_list("value", flat=True)

    def get_snapshots(self):
        if not self.uuids:
            self.get_uuids()

        self.snapshots = [Snapshot(u) for u in self.uuids]

    def get_last_snapshot(self):
        annotations = self.get_annotations()
        if annotations:
            annotation = annotations.first()
        self.last_snapshot = Snapshot(annotation.uuid)

    def last_uuid(self):
        return self.uuids[0]

    @classmethod
    def get_unassigned(cls, user):
        chids = DeviceLot.objects.filter(lot__owner=user).values_list("device_id", flat=True).distinct()
        annotations = Annotation.objects.filter(
            owner=user,
            type=Annotation.Type.SYSTEM,
        ).exclude(value__in=chids).values_list("value", flat=True).distinct()
        return [cls(id=x) for x in annotations]

        # return cls.objects.filter(
        #     owner=user
        #     ).annotate(num_lots=models.Count('lot')).filter(num_lots=0)

    @property
    def manufacturer(self):
        if not self.last_snapshot:
            self.get_last_snapshot()
        return self.last_snapshot.doc['device']['manufacturer']

    @property
    def type(self):
        if not self.last_snapshot:
            self.get_last_snapshot()
        return self.last_snapshot.doc['device']['type']

    @property
    def model(self):
        if not self.last_snapshot:
            self.get_last_snapshot()
        return self.last_snapshot.doc['device']['model']

    @property
    def type(self):
        if not self.last_snapshot:
            self.get_last_snapshot()
        return self.last_snapshot.doc['device']['type']
