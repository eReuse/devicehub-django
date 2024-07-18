from django.db import models

from utils.constants import STR_SM_SIZE, STR_SIZE, STR_EXTEND_SIZE, ALGOS
from snapshot.models import Annotation, Snapshot
from user.models import User


class Device(models.Model):
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

    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    type = models.CharField(max_length=STR_SIZE, blank=True, null=True)
    manufacturer = models.CharField(max_length=STR_EXTEND_SIZE, blank=True, null=True)
    model = models.CharField(max_length=STR_EXTEND_SIZE, blank=True, null=True)

    def __init__(self, *args, **kwargs):
        self.annotations =  []
        self.hids = []
        self.uuids = []
        self.snapshots = []
        super().__init__(*args, **kwargs)

    def initial(self):
        self.get_annotations()
        self.get_uuids()
        self.get_hids()
        self.get_snapshots()
        
    def get_annotations(self):
        self.annotations = Annotation.objects.filter(
            device=self,
            owner=self.owner
        ).order_by("-created")
            
    def get_uuids(self):
        for a in self.annotations:
            if not a.uuid in self.uuids:
                self.uuids.append(a.uuid)

    def get_hids(self):
        if not self.annotations:
            self.get_annotations()

        self.hids = self.annotations.filter(
            type=Annotation.Type.SYSTEM,
            key__in=ALGOS.keys(),
        ).values_list("value", flat=True)

    def get_snapshots(self):
        if not self.uuids:
            self.get_uuids()

        self.snapshots = [Snapshot(u) for u in self.uuids]

    def get_last_snapshot(self):
        if not self.snapshots:
            self.get_snapshots()

        if self.snapshots:
            return self.snapshots[0]

    @classmethod
    def get_unassigned(cls, user):
        return cls.objects.filter(
            owner=user
            ).annotate(num_lots=models.Count('lot')).filter(num_lots=0)
