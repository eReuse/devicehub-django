from django.db import models
from django.utils.translation import gettext_lazy as _
from utils.constants import (
    STR_SM_SIZE,
    STR_SIZE,
    STR_EXTEND_SIZE,
)

from user.models import User, Institution
from evidence.models import Property
# from device.models import Device


class LotTag(models.Model):
    name = models.CharField(max_length=STR_SIZE, blank=False, null=False)
    owner = models.ForeignKey(Institution, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    inbox = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class DeviceLot(models.Model):
    lot = models.ForeignKey("Lot", on_delete=models.CASCADE)
    device_id = models.CharField(max_length=STR_EXTEND_SIZE, blank=False, null=False)


class Lot(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    name = models.CharField(max_length=STR_SIZE, blank=True, null=True)
    code = models.CharField(max_length=STR_SIZE, blank=True, null=True)
    description = models.CharField(max_length=STR_SIZE, blank=True, null=True)
    archived = models.BooleanField(default=False)
    owner = models.ForeignKey(Institution, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    type = models.ForeignKey(LotTag, on_delete=models.CASCADE)

    def add(self, v):
        if DeviceLot.objects.filter(lot=self, device_id=v).exists():
            return
        DeviceLot.objects.create(lot=self, device_id=v)

    def remove(self, v):
        for d in DeviceLot.objects.filter(lot=self, device_id=v):
            d.delete()

class LotProperty(Property):
    lot  = models.ForeignKey(Lot, on_delete=models.CASCADE)

    class Type(models.IntegerChoices):
        SYSTEM = 0, "System"
        USER = 1, "User"

    type = models.SmallIntegerField(choices=Type.choices, default=Type.USER)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["key", "lot"], name="property_unique_type_key_lot")
        ]
