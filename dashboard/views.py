import json
import logging

from tablib import Dataset

from django.utils.translation import gettext_lazy as _
from django.views.generic.edit import FormView
from django.shortcuts import Http404
from django.utils.dateparse import parse_datetime
from django.http import HttpResponse
from dashboard.tables import DeviceTable

from django_tables2 import RequestConfig
from django_tables2.views import SingleTableMixin
from django_tables2.export.export import TableExport
from django_tables2.export.views import ExportMixin

from action.models import StateDefinition
from django.db.models import Q

from dashboard.mixins import InventaryMixin, DetailsMixin, DeviceTableMixin
from evidence.models import SystemProperty
from evidence.xapian import search
from device.models import Device
from lot.models import Lot, LotSubscription, Donor

logger = logging.getLogger('django')

class UnassignedDevicesView(DeviceTableMixin, InventaryMixin):
    template_name = "unassigned_devices.html"
    section = _("Inbox")
    title = _("Inbox")
    breadcrumb = f"{_('Devices')} / {_('Inbox')}"

    def get_devices(self, user, offset=0, limit=None):
        return Device.get_unassigned(self.request.user.institution, offset, limit)


class AllDevicesView(DeviceTableMixin, InventaryMixin):
    template_name = "unassigned_devices.html"
    section = _("All")
    title = _("All Devices")
    breadcrumb = f"{_('Devices')} / {_('All')}"

    def get_devices(self, user, offset=0, limit=None):
        return Device.get_all(self.request.user.institution, offset, limit)


class LotDashboardView(ExportMixin, SingleTableMixin, InventaryMixin, DetailsMixin):
    template_name = "unassigned_devices.html"
    section = "dashboard_lot"
    breadcrumb = f"{_('Lot')} / {_('Devices')}"
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
        subscriptions = LotSubscription.objects.filter(
            lot=lot,
            user=self.request.user
        )
        is_shop = subscriptions.filter(type=LotSubscription.Type.SHOP).first()
        is_circuit_manager = subscriptions.filter(
            type=LotSubscription.Type.CIRCUIT_MANAGER
        ).first()

        donor = Donor.objects.filter(lot=lot).first()

        context.update({
            'title': "{} {}".format(_("Lot"), lot.name),
            'lot': lot,
            'count': len(self.get_queryset()),
            'paginate_choices': self.paginate_choices,
            'state_definitions': self._get_state_definitions(),
            'limit': int(self.request.GET.get('limit', self.paginate_by)),
            'search_query': self.request.GET.get('q', ''),
            'breadcrumb' : _("Lot / {} / Devices").format(
                lot.name),
            'subscripted': subscriptions.first(),
            'is_circuit_manager': is_circuit_manager,
            'is_shop': is_shop,
            'donor': donor,
        })
        return context

    def get_queryset(self):
        chids = self.object.devicelot_set.all().values_list(
            "device_id", flat=True
        ).distinct()
        search_query = self.request.GET.get('q', '').lower()

        if search_query:
            ldevices = []
            for x in chids:
                dev = Device(id=x)
                if dev.matches_query(search_query):
                    ldevices.append(dev)
            return ldevices

        owner = self.request.user.institution
        return [Device(id=x, lot=self.object, owner=owner) for x in chids]

    def get_table_data(self):
        table_data = []
        for device in super().get_table_data():

            current_state = device.get_current_state()

            table_data.append({
                'id': device.pk,
                'shortid': device.shortid,
                'type': device.type,
                'manufacturer': getattr(device, 'manufacturer', ''),
                'model': getattr(device, 'model', ''),
                'version': getattr(device, 'version', ''),
                'cpu': getattr(device, 'cpu', ''),
                'current_state': current_state.state if current_state else '--',
                'status_beneficiary': device.status_beneficiary,
                'last_updated': parse_datetime(device.updated) if device.updated else "--"
            })
        return table_data

    def get_table_kwargs(self):
        kwargs = super().get_table_kwargs()
        limit = int(self.request.GET.get('limit', self.paginate_by))
        page = int(self.request.GET.get('page', 1))

        if limit != 0:
            self.table_pagination = {
                'per_page': limit,
                'page': page
            }
        else:
            self.table_pagination = False

        return kwargs

    def _get_state_definitions(self):
        return StateDefinition.objects.filter(
            institution=self.request.user.institution
        ).order_by('order')

    def create_export(self, export_format):
        if export_format in ('csv', 'xlsx'):

            devices = self.get_queryset()

            headers = [
                'ID', 'type', 'manufacturer', 'model', 'cpu_model', 'cpu_cores', 'current_state',
                'ram_total', 'ram_type', 'ram_slots', 'slots_used', 'drive', 'gpu_model', 'user_properties','serial', 'last_updated',
            ]
            data = Dataset(headers=headers)

            for device in devices:
                row_data = device.components_export()
                row_values = [
                    row_data['ID'],
                    row_data['type'],
                    row_data['manufacturer'],
                    row_data['model'],
                    row_data['cpu_model'],
                    row_data['cpu_cores'],
                    row_data['current_state'],
                    row_data['ram_total'],
                    row_data['ram_type'],
                    row_data['ram_slots'],
                    row_data['slots_used'],
                    row_data['drive'],
                    row_data['gpu_model'],
                    row_data['user_properties'],
                    row_data['serial'],
                    row_data['last_updated']
                ]
                data.append(row_values)

            content_types = {
                'csv': 'text/csv',
                'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            }
            response = HttpResponse(
                content=data.export(export_format),
                content_type=content_types[export_format],
                headers={
                    'Content-Disposition': f'attachment; filename="{self.object.name}_lot.{export_format}"'
                }
            )
            return response

        return super().create_export(export_format)

class SearchView(DeviceTableMixin, InventaryMixin):
    template_name = "unassigned_devices.html"
    section = _("Search")
    title = _("Search Devices")
    breadcrumb = f"{_('All Devices')} / {_('Search')}"

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

        count = search(
            self.request.user.institution,
            query[0],
            0,
            9999
        ).size()

        if count > 0:
            matches = search(
                self.request.user.institution,
                query[0],
                offset,
                limit
            )

            devices = []
            dev_id = set()

            for x in matches:
                # devices.append(self.get_annotations(x))
                try:
                    dev = self.get_properties(x)
                    if dev.id not in dev_id:
                        devices.append(dev)
                        dev_id.add(dev.id)
                except Exception as err:
                    logger.error("Error: {}".format(err))
                    continue
            # TODO fix of pagination, the count is not correct
            return devices, len(dev_id)

        return self.search_hids(query, offset, limit)

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
                qry |= Q(value__contains=i)

        chids = SystemProperty.objects.filter(
            owner=self.request.user.institution
        ).filter(
            qry
        ).values_list("value", flat=True).distinct()
        chids_page = chids[offset:offset+limit]

        return [Device(id=x) for x in chids_page], chids.count()
