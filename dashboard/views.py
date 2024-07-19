import json

from django.utils.translation import gettext_lazy as _
from django.db.models import Count
from dashboard.mixins import InventaryMixin, DetailsMixin
from device.models import Device
from snapshot.xapian import search
from snapshot.models import Annotation
from lot.models import Lot, LotTag


class UnassignedDevicesView(InventaryMixin):
    template_name = "unassigned_devices.html"
    section = "Unassigned"
    title = _("Unassigned Devices")
    breadcrumb = "Devices / Unassigned Devices"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        devices = Device.get_unassigned(self.request.user)

        context.update({
            'devices': devices,
        })

        return context


class LotDashboardView(InventaryMixin, DetailsMixin):
    template_name = "unassigned_devices.html"
    section = "dashboard_lot"
    title = _("Lot Devices")
    breadcrumb = "Lot / Devices"
    model = Lot

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        devices = self.get_devices()
        context.update({
            'devices': devices,
        })
        return context

    def get_devices(self):
        chids = self.object.devicelot_set.all().values_list("device_id", flat=True).distinct()
        return [Device(id=x) for x in chids]
