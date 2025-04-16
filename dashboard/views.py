import json

from django.utils.translation import gettext_lazy as _
from django.views.generic.edit import FormView
from django.shortcuts import Http404
from django.utils.dateparse import parse_datetime
from dashboard.tables import DeviceTable

from django_tables2 import RequestConfig
from django_tables2.views import SingleTableMixin
from django_tables2.export.views import ExportMixin
from django_tables2.export.export import TableExport

from action.models import StateDefinition
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


class LotDashboardView(ExportMixin, SingleTableMixin, InventaryMixin, DetailsMixin):
    template_name = "unassigned_devices.html"
    section = "dashboard_lot"
    title = _("Lot Devices")
    breadcrumb = "Lot / Devices"
    paginate_by = 10
    paginate_choices = [10, 20, 50, 100, 0]
    table_class = DeviceTable
    model = Lot
    export_formats = ['csv']
    export_name = 'lot_devices_export'
    table_pagination = {
        'per_page': paginate_by,
        'page': 1
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lot = context.get('object')
        self.object = lot

        context.update({
            'lot': lot,
            'count': len(self.get_queryset()),
            'paginate_choices': self.paginate_choices,
            'state_definitions': self._get_state_definitions(),
            'limit': int(self.request.GET.get('limit', self.paginate_by)),
            'search_query': self.request.GET.get('q', ''),
        })
        return context

    def get_queryset(self):
        search_query = self.request.GET.get('q', '').lower()
        device_ids = self._get_device_ids()
        device_details = self._get_device_details(device_ids)
        devices = list(device_details.keys())

        if search_query:
            devices = self._filter_devices(devices, device_details, search_query)

        return devices

    def get_table_data(self):
        table_data = []
        for device in super().get_table_data():
            device.initial()
            current_state = device.get_current_state()

            cpu_model = ""
            hdd_size = ""
            hdd_type = ""
            ram_type = ""
            total_ram_gb = 0


            if hasattr(device, 'components'):
                for component in device.components:

                    #TODO: do switch/case statement
                    if component.get('type') == 'Processor':
                        cpu_model = component.get('model', '')

                    elif component.get('type') == 'Storage':
                        interface = component.get('interface', '').upper()
                        if 'HDD' in interface:
                            hdd_type = 'HDD'
                        elif 'SSD' in interface:
                            hdd_type = 'SSD'
                        hdd_size = component.get('size', '')

                    elif component.get('type') == 'RamModule':
                        ram_type = component.get('interface', '')

                        size = component.get('size')
                        if size:
                            if isinstance(size, (int, float)):
                                total_ram_gb += float(size)
                            elif isinstance(size, str):
                                try:
                                    size_num = float(''.join(filter(lambda x: x.isdigit() or x == '.', size)))
                                    if 'GB' in size.upper() or 'GIB' in size.upper():
                                        total_ram_gb += size_num * 1024
                                    elif 'MB' in size.upper() or 'MIB' in size.upper():
                                        total_ram_gb += size_num
                                except (ValueError, AttributeError):
                                    pass

            table_data.append({
                'id': device.pk,
                'shortid': device.shortid,
                'type': device.type,
                'manufacturer': getattr(device, 'manufacturer', ''),
                'model': getattr(device, 'model', ''),
                'version': getattr(device, 'version', ''),
                'cpu': cpu_model,
                'hdd_size': hdd_size,
                'hdd_type': hdd_type,
                'ram_type': ram_type,
                'total_ram': f"{total_ram_gb:.1f} MB" if total_ram_gb else "",
                'current_state': current_state.state if current_state else '--',
                'last_updated': parse_datetime(device.updated) if device.updated else "--"
            })
        return table_data

    def get_table_kwargs(self):
        kwargs = super().get_table_kwargs()
        limit = int(self.request.GET.get('limit', self.paginate_by))
        page = int(self.request.GET.get('page', 1))

        self.table_pagination = {
            'per_page': limit,
            'page': page
        } if limit != 0 else False

        return kwargs

    def _get_state_definitions(self):
        return StateDefinition.objects.filter(
            institution=self.request.user.institution
        ).order_by('order')

    def _get_device_ids(self):
        return self.object.devicelot_set.values_list(
            "device_id", flat=True
        ).distinct()

    def _get_device_details(self, device_ids):
        props = SystemProperty.objects.filter(
            owner=self.request.user.institution,
            value__in=device_ids
        ).order_by("-created")

        device_map = {}
        for prop in props:
            device_id = prop.value
            if device_id not in device_map:
                device = Device(id=device_id)
                current_state = device.get_current_state()
                device_map[device] = {
                    'manufacturer': (device.manufacturer or '').lower(),
                    'model': (device.model or '').lower(),
                    'state': (current_state.state if current_state else '').lower(),
                    'shortid': (device.shortid or '').lower(),
                }
        return device_map

    def _filter_devices(self, devices, details, query):
        return [
            device for device in devices
            if any(query in details[device][field] for field in ['manufacturer', 'model', 'state', 'shortid'])
        ]


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
