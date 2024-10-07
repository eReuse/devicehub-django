from django.utils.translation import gettext_lazy as _
from django.shortcuts import Http404

from dashboard.mixins import InventaryMixin, DetailsMixin
from device.models import Device
from lot.models import Lot


class UnassignedDevicesView(InventaryMixin):
    template_name = "unassigned_devices.html"
    section = "Unassigned"
    title = _("Unassigned Devices")
    breadcrumb = "Devices / Unassigned Devices"

    def get_devices(self, user, offset, limit):
        return Device.get_unassigned(self.request.user.institution, offset, limit)


class LotDashboardView(InventaryMixin, DetailsMixin):
    template_name = "unassigned_devices.html"
    section = "dashboard_lot"
    title = _("Lot Devices")
    breadcrumb = "Lot / Devices"
    model = Lot

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lot = context.get('object')
        context.update({
            'lot': lot,
        })
        return context

    def get_devices(self, user, offset, limit):
        chids = self.object.devicelot_set.all().values_list("device_id", flat=True).distinct()
        chids_page = chids[offset:offset+limit]
        return [Device(id=x) for x in chids_page], chids.count()
