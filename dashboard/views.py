from django.utils.translation import gettext_lazy as _
from django.db.models import Count
from dashboard.mixins import InventaryMixin, DetailsMixin
from device.models import Device
from lot.models import Lot


class UnassignedDevicesView(InventaryMixin):
    template_name = "unassigned_devices.html"
    section = "Unassigned"
    title = _("Unassigned Devices")
    breadcrumb = "Devices / Unassigned Devices"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        devices = Device.objects.filter(
                owner=self.request.user
            ).annotate(num_lots=Count('lot')).filter(num_lots=0)
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
