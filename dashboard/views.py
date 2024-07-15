import json

from django.utils.translation import gettext_lazy as _
from django.db.models import Count
from dashboard.mixins import InventaryMixin, DetailsMixin
from device.models import Device
from snapshot.xapian import search
from snapshot.models import Annotation
from lot.models import Lot


class UnassignedDevicesView(InventaryMixin):
    template_name = "unassigned_devices.html"
    section = "Unassigned"
    title = _("Unassigned Devices")
    breadcrumb = "Devices / Unassigned Devices"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        annotations = Annotation.objects.filter(
                owner=self.request.user).filter(
                key="hidalgo1").order_by('created')
            # 'created').distinct('value')
            # ).annotate(num_lots=Count('lot')).filter(num_lots=0)

        hids = {}
        ids = []
        for x in annotations:
            if not hids.get(x.key):
                hids[x.key] = x.uuid
                ids.append(str(x.uuid))

        devices = []
        for xa in search(ids):
            # import pdb; pdb.set_trace()
            snap = json.loads(xa.document.get_data())
            dev = snap.get("device", {})
            dev["id"] = snap["uuid"]
            devices.append(dev)

        context.update({
            'devices': devices
        })
        return context


class AllDevicesView(InventaryMixin):
    template_name = "unassigned_devices.html"
    section = "All"
    title = _("All Devices")
    breadcrumb = "Devices / All Devices"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        devices = Device.objects.filter(owner=self.request.user)
        context.update({
            'devices': devices,
        })
        return context


class LotDashboardView(InventaryMixin, DetailsMixin):
    template_name = "unassigned_devices.html"
    section = "Unassigned"
    title = _("Lot Devices")
    breadcrumb = "Devices / Lot Devices"
    model = Lot

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        devices = self.object.devices.filter(owner=self.request.user)
        context.update({
            'devices': devices,
        })
        return context
