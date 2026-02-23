import json
import logging
import re

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

from action.models import StateDefinition, State
from django.db.models import Q, Subquery, OuterRef

from dashboard.mixins import InventaryMixin, DetailsMixin, DeviceTableMixin
from evidence.models import SystemProperty, RootAlias
from evidence.xapian import search
from device.models import Device
from lot.models import Lot, LotSubscription, Donor, DeviceLot, DeviceBeneficiary

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

    def _get_chids_qs(self):
        return self.object.devicelot_set.all().values_list(
            "device_id", flat=True
        ).distinct()

    def get_context_data(self, **kwargs):
        # super() creates and paginates the table via SingleTableMixin
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

        # Enrich the current page rows (already SQL-paginated) with Device data
        table = context['table']
        owner = self.request.user.institution
        for row in table.paginated_rows:
            device = Device(id=row.record['id'], lot=lot, owner=owner)
            current_state = device.get_current_state()
            row.record.update({
                'shortid': device.shortid,
                'type': device.type,
                'manufacturer': getattr(device, 'manufacturer', ''),
                'model': getattr(device, 'model', ''),
                'version': getattr(device, 'version', ''),
                'cpu': getattr(device, 'cpu', ''),
                'status_beneficiary': device.status_beneficiary,
                'current_state': current_state.state if current_state else '--',
                'last_updated': parse_datetime(device.updated) if device.updated else '--',
            })

        limit = int(self.request.GET.get('limit', self.paginate_by))
        page = int(self.request.GET.get('page', 1))
        search_query = self.request.GET.get('q', '')
        if search_query:
            count = getattr(self, '_search_count', len(list(table.rows)))
        else:
            count = getattr(self, '_total_count', 0)
        total_pages = (count + limit - 1) // limit if limit else 1

        context.update({
            'title': "{} {}".format(_("Lot"), lot.name),
            'lot': lot,
            'count': count,
            'page': page,
            'total_pages': total_pages,
            'paginate_choices': self.paginate_choices,
            'state_definitions': self._get_state_definitions(),
            'limit': limit,
            'search_query': self.request.GET.get('q', ''),
            'sort': self.request.GET.get('sort', ''),
            'breadcrumb': _("Lot / {} / Devices").format(lot.name),
            'subscripted': subscriptions.first(),
            'is_circuit_manager': is_circuit_manager,
            'is_shop': is_shop,
            'donor': donor,
        })
        return context

    def get_queryset(self):
        chids = self._get_chids_qs()
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
        institution = self.request.user.institution
        search_query = self.request.GET.get('q', '').lower()
        chids = self._get_chids_qs()

        if search_query:
            devices = []
            for x in chids:
                dev = Device(id=x)
                if dev.matches_query(search_query):
                    devices.append(dev)
            self._search_count = len(devices)
            # Return full records immediately for search (Device objects already created)
            table_data = []
            for device in devices:
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
                    'last_updated': parse_datetime(device.updated) if device.updated else '--',
                })
            return table_data

        # Non-search: batch queries + Python sort, no correlated subqueries.
        # Correlated subqueries force SQLite to evaluate all N rows even with
        # LIMIT because DISTINCT + ORDER BY requires a full scan first.

        # Phase 1: all device_ids for the lot
        device_ids = list(chids)
        self._total_count = len(device_ids)
        if not device_ids:
            return []

        # Phase 2: batch-fetch sort keys with simple IN queries
        # last_updated + latest uuid per device (one pass over SystemProperty)
        sp_info = {}  # device_id -> {'date': datetime, 'uuid': uuid}
        for sp in SystemProperty.objects.filter(
            owner=institution, value__in=device_ids
        ).order_by('-created').values('value', 'uuid', 'created'):
            if sp['value'] not in sp_info:
                sp_info[sp['value']] = {'date': sp['created'], 'uuid': sp['uuid']}

        # current_state: latest state per device via UUID
        device_uuids = [info['uuid'] for info in sp_info.values()]
        state_by_uuid = {}
        for state in State.objects.filter(
            snapshot_uuid__in=device_uuids
        ).order_by('-date').values('snapshot_uuid', 'state'):
            key = str(state['snapshot_uuid'])
            if key not in state_by_uuid:
                state_by_uuid[key] = state['state']

        # beneficiary status per device
        beneficiary_statuses = {
            row['device_id']: row['status']
            for row in DeviceBeneficiary.objects.filter(
                device_id__in=device_ids,
                beneficiary__lot=self.object,
            ).values('device_id', 'status')
        }

        # Phase 3: sort in Python
        sort_param = self.request.GET.get('sort', '-last_updated')
        reverse = sort_param.startswith('-')
        sort_field = sort_param.lstrip('-')

        def get_sort_val(did):
            if sort_field == 'last_updated':
                info = sp_info.get(did)
                return info['date'] if info else None
            if sort_field == 'current_state':
                info = sp_info.get(did)
                uuid = info['uuid'] if info else None
                return state_by_uuid.get(str(uuid)) if uuid else None
            if sort_field == 'status_beneficiary':
                return beneficiary_statuses.get(did, 0)
            return did  # shortid fallback

        none_ids = [did for did in device_ids if get_sort_val(did) is None]
        val_ids  = [did for did in device_ids if get_sort_val(did) is not None]
        sorted_ids = sorted(val_ids, key=get_sort_val, reverse=reverse) + none_ids

        # Phase 4: paginate
        limit = int(self.request.GET.get('limit', self.paginate_by))
        page  = int(self.request.GET.get('page', 1))
        offset = (page - 1) * limit if limit else 0
        page_ids = sorted_ids[offset:offset + limit] if limit else sorted_ids

        # Phase 5: batch RootAlias only for current page
        root_aliases = {
            ra.alias: ra.root
            for ra in RootAlias.objects.filter(owner=institution, alias__in=page_ids)
        }

        return [
            {
                'id': did,
                'shortid': root_aliases.get(did, did).split(':')[1][:6].upper(),
                'current_state': (
                    state_by_uuid.get(str(sp_info[did]['uuid']))
                    if did in sp_info else None
                ) or '--',
                'last_updated': sp_info.get(did, {}).get('date'),
                'status_beneficiary': beneficiary_statuses.get(did, 0),
                'type': '',
                'manufacturer': '',
                'model': '',
                'version': '',
                'cpu': '',
            }
            for did in page_ids
        ]

    def get_table_kwargs(self):
        kwargs = super().get_table_kwargs()
        # Pagination is handled at SQL level; disable django-tables2 pagination
        self.table_pagination = False

        if not self.object.beneficiary_set.exists():
            kwargs['exclude'] = ('status_beneficiary',)

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
    table_order_by = ()  # override DeviceTable.Meta order_by=("-last_updated",) to preserve relevance order

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        search_params = self.request.GET.urlencode(),
        search = self.request.GET.get("search")
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

        query_str = query[0]

        # 1. Shortid search (DB only, no JSON)
        sp_ids = self._search_shortid_ids(query_str)
        sp_count = len(sp_ids)

        # 2. Xapian: count (no JSON) + page (JSON only for page documents)
        sp_page = sp_ids[offset:offset + limit]
        xapian_needed = limit - len(sp_page)
        xapian_offset = max(0, offset - sp_count)
        xapian_count = self._get_xapian_count(query_str)
        xapian_page = self._search_xapian_page(
            query_str, xapian_offset, xapian_needed
        )
        total = sp_count + xapian_count

        page_ids = sp_page + xapian_page
        devices = [Device(id=x) for x in page_ids]

        return devices, total

    def _search_shortid_ids(self, query_str):
        """Search SystemProperty by shortid. Returns a list of canonical device
        IDs sorted by relevance (exact shortid match first, partial second)."""
        terms = [t for t in query_str.split() if t]
        if not terms:
            return []

        institution = self.request.user.institution

        # Query 1: term starts at position 0 of the hash (highest relevance)
        exact_qry = Q()
        for term in terms:
            exact_qry |= Q(value__iregex=r'^[^:]+:' + re.escape(term))

        exact_values = list(
            SystemProperty.objects.filter(owner=institution)
            .filter(exact_qry)
            .values_list("value", flat=True)
            .distinct()
        )

        # Query 2: term appears within the shortid but NOT at position 0
        partial_values = []
        partial_qry = Q()
        for term in terms:
            max_offset = 6 - len(term)
            if max_offset > 0:
                rqry = r'^[^:]+:[^:]{1,' + str(max_offset) + r'}' + re.escape(term)
                partial_qry |= Q(value__iregex=rqry)

        if partial_qry:
            seen_exact = set(exact_values)
            partial_values = [
                v for v in SystemProperty.objects.filter(owner=institution)
                .filter(partial_qry)
                .values_list("value", flat=True)
                .distinct()
                if v not in seen_exact
            ]

        values = exact_values + partial_values

        if not values:
            return []

        # Resolve aliases to root values in bulk
        alias_map = dict(
            RootAlias.objects.filter(owner=institution, alias__in=values)
            .values_list("alias", "root")
        )

        seen = set()
        ids = []
        for value in values:
            canonical = alias_map.get(value, value)
            if canonical not in seen:
                seen.add(canonical)
                ids.append(canonical)

        return ids

    def _get_xapian_count(self, query_str):
        """Return the number of xapian document matches (no JSON parsing)."""
        matches = search(self.request.user.institution, query_str, 0, 9999)
        if not matches:
            return 0
        return matches.size()

    def _search_xapian_page(self, query_str, offset, limit):
        """Fetch one page of xapian results. JSON is parsed only for the
        documents in this page. No deduplication: one xapian document = one result."""
        if limit <= 0:
            return []

        institution = self.request.user.institution
        matches = search(institution, query_str, offset, limit)
        if not matches or matches.size() == 0:
            return []

        uuids = []
        for x in matches:
            try:
                snap = json.loads(x.document.get_data())
                if snap.get("credentialSubject"):
                    uuid = snap["credentialSubject"]["uuid"]
                else:
                    uuid = snap["uuid"]
                uuids.append(uuid)
            except Exception as err:
                logger.error("Error: {}".format(err))

        if not uuids:
            return []

        props = SystemProperty.objects.filter(
            owner=institution,
            uuid__in=uuids,
        ).values_list("uuid", "value")
        uuid_to_value = {str(u): v for u, v in props}

        return [uuid_to_value[uuid] for uuid in uuids if uuid in uuid_to_value]
