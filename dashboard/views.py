import json
from tablib import Dataset

from django.utils.translation import gettext_lazy as _
from django.utils.dateparse import parse_datetime
from django.http import HttpResponse
from dashboard.tables import DeviceTable
from django.core.cache import cache
from collections import Counter

from django_tables2.views import SingleTableMixin
from django_tables2.export.views import ExportMixin
from django.contrib.auth.mixins import LoginRequiredMixin

from action.models import StateDefinition
from django.db.models import Q, Count, Subquery, OuterRef, F, CharField, Value
from lot.models import DeviceLot
from django.db.models.functions import Coalesce
from django.views.generic import TemplateView

from dashboard.mixins import InventaryMixin, DetailsMixin, DeviceTableMixin
from evidence.models import SystemProperty
from evidence.xapian import search
from device.models import Device
from lot.models import Lot, LotSubscription, Donor
from action.models import State


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
            return [
                Device(id=x) for x in chids
                if Device(id=x).matches_query(search_query)
            ]

        return [Device(id=x, lot=self.object) for x in chids]

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
                dev = self.get_properties(x)
                if dev.id not in dev_id:
                    devices.append(dev)
                    dev_id.add(dev.id)

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
                qry |= Q(value__startswith=i)

        chids = SystemProperty.objects.filter(
            owner=self.request.user.institution
        ).filter(
            qry
        ).values_list("value", flat=True).distinct()
        chids_page = chids[offset:offset+limit]

        return [Device(id=x) for x in chids_page], chids.count()

class InventoryOverviewView(LoginRequiredMixin, TemplateView):
    """
    A view to display "at-a-glance" dashboard statistics for the
    device inventory.

    This view is CACHED because it must perform slow operations
    (instantiating Device() for all devices) to get
    statistics on non-SQL fields like device type.
    """
    template_name = 'inventory_overview.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if not hasattr(self.request.user, 'institution'):
            context['error'] = 'User is not associated with an institution.'
            return context

        institution = self.request.user.institution
        cache_key = f"dashboard_stats_{institution.id}"

        cache.delete(cache_key)
        cached_context = cache.get(cache_key)
        if cached_context:
            context.update(cached_context)
            return context


        # getting all devices ID
        all_device_ids_list, _ = Device.get_all(institution, limit=None)
        unassigned_device_ids_list, _ = Device.get_unassigned(institution, limit=None)
        unassigned_ids_set = {d.id for d in unassigned_device_ids_list}

        total_devices = len(all_device_ids_list)
        unassigned_devices = len(unassigned_ids_set)
        assigned_devices = total_devices - unassigned_devices

        # States
        latest_prop_created_sq = SystemProperty.objects.filter(value=OuterRef('value'), owner=institution).order_by('-created')
        latest_uuid_sq = SystemProperty.objects.filter(value=OuterRef('value'), created=Subquery(latest_prop_created_sq.values('created')[:1])).values('uuid')[:1]
        latest_state_name_sq = State.objects.filter(snapshot_uuid=OuterRef('latest_uuid')).order_by('-date')
        device_state_qset = SystemProperty.objects.filter(
            owner=institution
        ).values('value').distinct().annotate(
            latest_uuid=Subquery(latest_uuid_sq),
            current_state_name=Subquery(latest_state_name_sq.values('state')[:1])
        ).values('value', 'current_state_name')
        device_id_to_state_map = {
            item['value']: item.get('current_state_name') or 'Unknown'
            for item in device_state_qset
        }

        # Lots
        device_id_to_lot_map = {}
        all_device_lots = DeviceLot.objects.filter(
            lot__owner=institution,
            lot__archived=False
        ).select_related('lot')
        for dl in all_device_lots:
            device_id_to_lot_map.setdefault(dl.device_id, []).append(dl.lot)


        # PROCESS ALL DEVICES IN BATCHES
        total_types_counter = Counter()
        assigned_types_counter = Counter()
        unassigned_types_counter = Counter()
        states_breakdown = {}
        lots_breakdown = {}

        batch_size = 250  # 250 at a time

        for i in range(0, total_devices, batch_size):
            # Get ids
            batch_id_objects = all_device_ids_list[i:i + batch_size]

            #instatiate by batch
            batch_devices = [Device(id=d.id) for d in batch_id_objects]

            for d in batch_devices:
                device_type = d.type or 'Unknown'
                total_types_counter[device_type] += 1

                is_assigned = d.id not in unassigned_ids_set

                if is_assigned:
                    assigned_types_counter[device_type] += 1
                else:
                    unassigned_types_counter[device_type] += 1

                state_name = device_id_to_state_map.get(d.id, 'Unknown')
                if state_name not in states_breakdown:
                    states_breakdown[state_name] = {'total': 0, 'types': Counter()}
                states_breakdown[state_name]['total'] += 1
                states_breakdown[state_name]['types'][device_type] += 1

                if is_assigned:
                    lots_for_device = device_id_to_lot_map.get(d.id, [])
                    for lot in lots_for_device:
                        if lot.pk not in lots_breakdown:
                            lots_breakdown[lot.pk] = {'name': lot.name, 'total': 0, 'types': Counter()}
                        lots_breakdown[lot.pk]['total'] += 1
                        lots_breakdown[lot.pk]['types'][device_type] += 1


        total_types_summary = dict(total_types_counter.most_common(4))
        assigned_types_summary = dict(assigned_types_counter.most_common(3))
        unassigned_types_summary = dict(unassigned_types_counter.most_common(3))

        states_summary = []
        for name, data in states_breakdown.items():
            states_summary.append({
                'state': name,
                'count': data['total'],
                'types': dict(data['types'].most_common(3))
            })
        states_summary = sorted(states_summary, key=lambda x: x['count'], reverse=True)

        lots_summary = []
        for pk, data in lots_breakdown.items():
            lots_summary.append({
                'pk': pk,
                'name': data['name'],
                'count': data['total'],
                'types': dict(data['types'].most_common(3))
            })
        lots_summary = sorted(lots_summary, key=lambda x: x['count'], reverse=True)[:10]

        final_context = {
            'total_devices': total_devices,
            'total_types_summary': total_types_summary,
            'unassigned_devices': unassigned_devices,
            'unassigned_types_summary': unassigned_types_summary,
            'assigned_devices': assigned_devices,
            'assigned_types_summary': assigned_types_summary,
            'lots_summary': lots_summary,
            'states_summary': states_summary,
        }

        cache.set(cache_key, final_context, timeout=600)
        context.update(final_context)
        return context
