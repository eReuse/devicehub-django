import json

from django.utils.translation import gettext_lazy as _
from django.views.generic.edit import FormView
from django.shortcuts import Http404
from django.db.models import Q

from dashboard.mixins import InventaryMixin, DetailsMixin, DeviceTableMixin
from evidence.models import SystemProperty
from evidence.xapian import search
from device.models import Device
from lot.models import Lot


class UnassignedDevicesView(DeviceTableMixin, InventaryMixin):
    template_name = "unassigned_devices.html"
    section = "Inbox"
    title = _("Inbox")
    breadcrumb = "Lot / Inbox"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return self.configure_table(context)

    def get_devices(self, user, offset=0, limit=None):
        return Device.get_unassigned(self.request.user.institution, offset, limit)


class AllDevicesView(DeviceTableMixin, InventaryMixin):
    template_name = "unassigned_devices.html"
    section = "All"
    title = _("All Devices")
    breadcrumb = "Devices / All Devices"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return self.configure_table(context)

    def get_devices(self, user, offset=0, limit=None):
        return Device.get_all(self.request.user.institution, offset, limit)


class LotDashboardView(DeviceTableMixin, InventaryMixin, DetailsMixin):
    template_name = "unassigned_devices.html"
    section = "dashboard_lot"
    title = _("Lot Devices")
    breadcrumb = "Lot / Devices"
    model = Lot

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lot = context.get('object')
        context.update({'lot': lot})
        return self.configure_table(context)

    def get_devices(self, user, offset=0, limit=None):
        search_query = self.request.GET.get('q', '').lower()
        chids = self.object.devicelot_set.all().values_list(
            "device_id", flat=True
        ).distinct()

        props = SystemProperty.objects.filter(
            owner=self.request.user.institution,
            value__in=chids
        ).order_by("-created")

        # Get all devices first to enable search filtering
        all_devices = []
        device_details = {}  # Store device details for searching
        for prop in props:
            if prop.value not in device_details:
                device = Device(id=prop.value)
                all_devices.append(device)
                # Store relevant searchable fields
                device_details[prop.value] = {
                    'manufacturer': device.manufacturer.lower() if device.manufacturer else '',
                    'model': device.model.lower() if device.model else '',
                    'state': device.get_current_state().state.lower() if device.get_current_state() else '',
                    'shortid': device.shortid.lower() if device.shortid else ''
                }

        # Apply search filter if query exists
        if search_query:
            filtered_devices = []
            for device in all_devices:
                details = device_details[device.id]
                if (search_query in details['manufacturer'] or
                    search_query in details['model'] or
                    search_query in details['state'] or
                    search_query in details['shortid']):
                    filtered_devices.append(device)
            all_devices = filtered_devices

        # Apply pagination
        total_count = len(all_devices)
        paginated_devices = all_devices[offset:offset+limit] if limit else all_devices

        return paginated_devices, total_count


class SearchView(DeviceTableMixin, InventaryMixin):
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

        return self.configure_table(context)

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
