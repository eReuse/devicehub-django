from django.db import models
from django.utils.translation import gettext_lazy as _
from utils.constants import STR_SM_SIZE, STR_SIZE

from user.models import User
from device.models import Device


class Lot(models.Model):
    class Types(models.TextChoices):
        INCOMING = "Incoming"
        OUTGOING = "Outgoing"
        TEMPORAL = "Temporal"

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    type = models.CharField(max_length=STR_SM_SIZE, choices=Types, default=Types.TEMPORAL)
    name = models.CharField(max_length=STR_SIZE, blank=True, null=True)
    code = models.CharField(max_length=STR_SIZE, blank=True, null=True)
    description = models.CharField(max_length=STR_SIZE, blank=True, null=True)
    closed = models.BooleanField(default=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    devices = models.ManyToManyField(Device)

    @property
    def is_incoming(self):
        if self.type == self.Types.INCOMING:
            return True
        return False

    @property
    def is_outgoing(self):
        if self.type == self.Types.OUTGOING:
                return True
        return False

    @property
    def is_temporal(self):
        if self.type == self.Types.TEMPORAL:
                return True
        return False
