import json

from django.utils.translation import gettext_lazy as _
from django.views.generic.edit import FormView
from django.shortcuts import Http404
from django.db.models import Q

from dashboard.mixins import InventaryMixin, DetailsMixin
from evidence.models import SystemProperty
from evidence.xapian import search
from device.models import Device
from lot.models import Lot


class UnassignedDevicesView(InventaryMixin):
    template_name = "unassigned_devices.html"
    section = "Unassigned"
    title = _("Unassigned Devices")
    breadcrumb = "Devices / Unassigned Devices"

    def get_devices(self, user, offset, limit):
        return Device.get_unassigned(self.request.user.institution, offset, limit)


class AllDevicesView(InventaryMixin):
    template_name = "unassigned_devices.html"
    section = "All"
    title = _("All Devices")
    breadcrumb = "Devices / All Devices"

    def get_devices(self, user, offset, limit):
        return Device.get_all(self.request.user.institution, offset, limit)


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
        chids = self.object.devicelot_set.all().values_list(
            "device_id", flat=True
        ).distinct()

        props = SystemProperty.objects.filter(
            owner=self.request.user.institution,
            value__in=chids
        ).order_by("-created")

        chids_ordered = []
        for x in props:
            if x.value not in chids_ordered:
                chids_ordered.append(x.value)

        chids_page = chids_ordered[offset:offset+limit]
        return [Device(id=x) for x in chids_page], len(chids_ordered)


class SearchView(InventaryMixin):
    template_name = "unassigned_devices.html"
    section = "Search"
    title = _("Search Devices")
    breadcrumb = "Devices / Search Devices"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        search_params = self.request.GET.urlencode(),
        search =  self.request.GET.get("search")
        if search:
            context.update({
                'search_params': search_params,
                'search': search
            })

        return context

    def get_devices(self, user, offset, limit):
        query = dict(self.request.GET).get("search")

        if not query:
            return [], 0

        matches = search(
            self.request.user.institution,
            query[0],
            offset,
            limit
        )
        count = search(
            self.request.user.institution,
            query[0],
            0,
            9999
        ).size()

        if not matches or not matches.size():
            return self.search_hids(query, offset, limit)

        devices = []
        dev_id = []

        for x in matches:
            # devices.append(self.get_annotations(x))
            dev = self.get_properties(x)
            if dev.id not in dev_id:
                devices.append(dev)
                dev_id.append(dev.id)

        # TODO fix of pagination, the count is not correct
        return devices, count

    def get_properties(self, xp):
        snap = json.loads(xp.document.get_data())
        if snap.get("credentialSubject"):
            uuid = snap["credentialSubject"]["uuid"]
        else:
            uuid = snap["uuid"]

        return Device.get_properties_from_uuid(uuid, self.request.user.institution)

    def search_hids(self, query, offset, limit):
        qry = Q()

        for i in query[0].split(" "):
            if i:
                qry |= Q(value__startswith=i)

        chids = SystemProperty.objects.filter(
            owner=self.request.user.institution
        ).filter(
            qry
        ).values_list("value", flat=True).distinct()
        chids_page = chids[offset:offset+limit]

        return [Device(id=x) for x in chids_page], chids.count()
