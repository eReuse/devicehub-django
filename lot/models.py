import uuid

from django.db import models
from django.db.models import Max
from django.utils.translation import gettext_lazy as _
from utils.constants import (
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
    order = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.pk:
            # set the order to be last
            max_order = LotTag.objects.filter(owner=self.owner).aggregate(Max('order'))['order__max']
            self.order = (max_order or 0) + 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        institution = self.owner
        order = self.order
        super().delete(*args, **kwargs)
        # Adjust the order of other instances
        LotTag.objects.filter(owner=institution, order__gt=order).update(order=models.F('order') - 1)


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

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['owner', 'name', 'type'], name='unique_institution_and_name')
        ]

    def add(self, v):
        if DeviceLot.objects.filter(lot=self, device_id=v).exists():
            return
        DeviceLot.objects.create(lot=self, device_id=v)

    def remove(self, v):
        for d in DeviceLot.objects.filter(lot=self, device_id=v):
            d.delete()

    @property
    def devices(self):
        return DeviceLot.objects.filter(lot=self)

    def device_count(self):
        return self.devices.count()


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


class LotSubscription(models.Model):
    class Type(models.IntegerChoices):
        CIRCUIT_MANAGER = 0, _("Circuit Manager")
        SHOP = 1, _("Shop")

    lot = models.ForeignKey(Lot, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=False, blank=False)
    type = models.SmallIntegerField(choices=Type.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["lot", "user"], name="unique_lot_user")
        ]

    @property
    def is_circuit_manager(self):
        return self.type == self.Type.CIRCUIT_MANAGER

    @property
    def is_shop(self):
        return self.type == self.Type.SHOP


class Donor(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reconciliation = models.DateTimeField(_("Reconciliation"), null=True, blank=True)
    lot = models.ForeignKey(Lot, on_delete=models.CASCADE)
    email = models.EmailField(
        _('Email address'),
        max_length=255,
    )


class Beneficiary(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sign_conditions = models.DateTimeField(_("Conditions"), null=True, blank=True)
    lot = models.ForeignKey(Lot, on_delete=models.CASCADE)
    shop = models.ForeignKey(LotSubscription, on_delete=models.CASCADE)
    email = models.EmailField(
        _('Email address'),
        max_length=255,
    )

    def add(self, v):
        exist = DeviceBeneficiary.objects.filter(
            beneficiary__lot=self.lot, device_id=v
        ).exists()

        if exist:
            return

        DeviceBeneficiary.objects.create(
            beneficiary=self,
            device_id=v,
            status=DeviceBeneficiary.Status.INTEREST
        )

    def remove(self, v):
        for d in DeviceBeneficiary.objects.filter(beneficiary=self, device_id=v):
            d.delete()


class DeviceBeneficiary(models.Model):
    class Status(models.IntegerChoices):
        AVAILABLE = 0, _("Available")
        INTEREST = 1, _("Interest")
        TRANSFER = 2, _("Transfer")
        CONFIRMED = 3, _("Confirmed")
        DELIVERED = 4, _("Delivered")
        RETURNED = 5, _("Returned")

    beneficiary = models.ForeignKey("Beneficiary", on_delete=models.CASCADE)
    device_id = models.CharField(max_length=STR_EXTEND_SIZE, blank=False, null=False)
    status = models.SmallIntegerField(choices=Status.choices, default=Status.AVAILABLE)
    returned_place = models.CharField(max_length=500, blank=True, null=True)
