from django.db import models
from django.utils.translation import gettext_lazy as _
from utils.constants import (
    STR_SM_SIZE,
    STR_SIZE,
    STR_EXTEND_SIZE,
)

from user.models import User
from device.models import Device
from snapshot.models import Annotation


class LotTag(models.Model):
    name = models.CharField(max_length=STR_SIZE, blank=False, null=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)

    def __str__(self):
        return self.name


class Lot(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    name = models.CharField(max_length=STR_SIZE, blank=True, null=True)
    code = models.CharField(max_length=STR_SIZE, blank=True, null=True)
    description = models.CharField(max_length=STR_SIZE, blank=True, null=True)
    closed = models.BooleanField(default=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    type = models.ForeignKey(LotTag, on_delete=models.CASCADE)
    devices = models.ManyToManyField(Device)
