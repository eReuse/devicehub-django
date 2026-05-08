import json
import logging
import re

from tablib import Dataset

from django.utils.translation import gettext_lazy as _
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.shortcuts import redirect
from django.contrib import messages
from django.http import HttpResponse
from dashboard.tables import DeviceTable
from django.core.cache import cache
from collections import Counter

from django_tables2.views import SingleTableMixin
from django_tables2.export.views import ExportMixin
from django.views.generic import TemplateView

from dashboard.mixins import InventaryMixin, DetailsMixin, DeviceTableMixin
from evidence.models import SystemProperty, RootAlias
from action.models import StateDefinition
from django.db.models import Q, Subquery, OuterRef
from lot.models import DeviceLot
from user.models import UserProfile
from django.views.generic import TemplateView

from dashboard.mixins import DashboardView, InventaryMixin, DetailsMixin, DeviceTableMixin
from evidence.models import SystemProperty
from evidence.xapian import search
from device.models import Device
from lot.models import Lot, LotSubscription, Donor, DeviceLot, DeviceBeneficiary
from action.models import StateDefinition, State

logger = logging.getLogger('django')

class UnassignedDevicesView(DeviceTableMixin, InventaryMixin):
    template_name = "unassigned_devices.html"
    section = _("Inbox")
    title = _("Inbox")
    breadcrumb = f"{_('Devices')} / {_('Inbox')}"

    def get_devices(self, user, offset=0, limit=None):
        return Device.get_unassigned(self.request.user.institution, offset, limit)

    def get_all_device_ids(self):
        devices, _ = self.get_devices(self.request.user, offset=0, limit=None)
        return [d.pk for d in devices]


class AllDevicesView(DeviceTableMixin, InventaryMixin):
    template_name = "unassigned_devices.html"
    section = _("All")
    title = _("All Devices")
    breadcrumb = f"{_('Devices')} / {_('All')}"

    def get_devices(self, user, offset=0, limit=None):
        return Device.get_all(self.request.user.institution, offset, limit)

    def get_all_device_ids(self):
        devices, _ = self.get_devices(self.request.user, offset=0, limit=None)
        return [d.pk for d in devices]


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

        table = context['table']
        owner = self.request.user.institution
        for row in table.paginated_rows:
            device = Device(id=row.record['id'], lot=lot, owner=owner)
            current_state = device.get_current_state()
            row.record.update({
                'shortid': device.shortid,
                'link_pk': device.link_pk,
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
            'title': "{} {} - {}".format(_("Lot"), lot.name, _("Devices")),
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
        owner = self.request.user.institution

        if search_query:
            ldevices = []
            for x in chids:
                dev = Device(id=x, lot=self.object, owner=owner)
                if dev.matches_query(search_query):
                    ldevices.append(dev)
            return ldevices

        return [Device(id=x, lot=self.object, owner=owner) for x in chids]

    def get_table_data(self):
        #TODO: check later on soft reset to main
        institution = self.request.user.institution
        search_query = self.request.GET.get('q', '').lower()
        chids = self._get_chids_qs()
        owner = self.request.user.institution

        if search_query:
            devices = []
            for x in chids:
                dev = Device(id=x, lot=self.object, owner=owner)
                if dev.matches_query(search_query):
                    devices.append(dev)
            self._search_count = len(devices)
            # return full records immediately for search (Device objects already created)
            table_data = []
            for device in devices:
                current_state = device.get_current_state()
                table_data.append({
                    'id': device.pk,
                    'link_pk': device.link_pk,
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

    def get_all_device_ids(self):
        if not hasattr(self, 'object') or self.object is None:
            self.object = get_object_or_404(
                self.model,
                pk=self.kwargs['pk'],
                owner=self.request.user.institution,
            )
        chids = list(self._get_chids_qs())
        search_query = self.request.GET.get('q', '').lower()
        if search_query:
            owner = self.request.user.institution
            chids = [x for x in chids if Device(id=x, lot=self.object, owner=owner).matches_query(search_query)]
        return chids

    def create_export(self, export_format):
        if export_format in ('csv', 'xlsx'):

            devices = self.get_queryset()

            headers = [
                'ID', 'type', 'manufacturer', 'model', 'serial',
                'current_state', 'last_updated',
                'cpu_model', 'cpu_cores', 'ram_total', 'ram_type',
                'ram_slots', 'slots_used', 'gpu_model',

                # Disk fields
                'drive', 'disk_capacity', 'disk_interface', 'disk_health',

                # Display fields
                'native_resolution', 'screen_size', 'gamma', 'color_format',

                'user_properties',
            ]
            data = Dataset(headers=headers)

            for device in devices:
                row_data = device.components_export()
                row_values = [row_data.get(h, '') for h in headers]
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
        devices = [Device(id=x, owner=user.institution) for x in page_ids]

        return devices, total

    def _build_shortid_qry(self, terms, field):
        exact_qry = Q()
        for term in terms:
            exact_qry |= Q(**{f"{field}__iregex": r'^[^:]+:' + re.escape(term)})

        partial_qry = Q()
        for term in terms:
            max_offset = 6 - len(term)
            if max_offset > 0:
                rqry = r'^[^:]+:[^:]{1,' + str(max_offset) + r'}' + re.escape(term)
                partial_qry |= Q(**{f"{field}__iregex": rqry})

        return exact_qry, partial_qry

    def _search_shortid_ids(self, query_str):
        """Search SystemProperty by shortid and RootAlias by root shortid.
        Returns a list of canonical device IDs sorted by relevance
        (exact shortid match first, partial second)."""
        terms = [t for t in query_str.split() if t]
        if not terms:
            return []

        institution = self.request.user.institution

        # Search in SystemProperty.value
        exact_qry, partial_qry = self._build_shortid_qry(terms, "value")

        exact_values = list(
            SystemProperty.objects.filter(owner=institution)
            .filter(exact_qry)
            .values_list("value", flat=True)
            .distinct()
        )

        seen_exact = set(exact_values)
        partial_values = []
        if partial_qry:
            partial_values = [
                v for v in SystemProperty.objects.filter(owner=institution)
                .filter(partial_qry)
                .values_list("value", flat=True)
                .distinct()
                if v not in seen_exact
            ]

        values = exact_values + partial_values

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

        # Search RootAlias.root directly by shortid
        exact_root_qry, partial_root_qry = self._build_shortid_qry(terms, "root")

        exact_roots = list(
            RootAlias.objects.filter(owner=institution)
            .filter(exact_root_qry)
            .values_list("root", flat=True)
            .distinct()
        )
        for root in exact_roots:
            if root not in seen:
                seen.add(root)
                ids.append(root)

        if partial_root_qry:
            partial_roots = [
                v for v in RootAlias.objects.filter(owner=institution)
                .filter(partial_root_qry)
                .values_list("root", flat=True)
                .distinct()
                if v not in seen
            ]
            for root in partial_roots:
                seen.add(root)
                ids.append(root)

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


class InventoryOverviewView(DashboardView, TemplateView):
    template_name = 'inventory_overview.html'
    section = _("Inbox")
    title = _("Overview")
    breadcrumb = f"{_('Devices')} / {_('Overview')}"

    def get(self, request, *args, **kwargs):
        if request.user.is_admin and request.GET.get('refresh') == 'true':
            if hasattr(request.user, 'institution'):
                institution = request.user.institution
                cache_key = f"dashboard_stats_institution_{institution.id}"
                cache.delete(cache_key)
                messages.success(request, _("Cache has been cleared. Data is refreshing."))

            return redirect('dashboard:overview')
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if not hasattr(self.request.user, 'institution'):
            context['error'] = 'User is not associated with an institution.'
            return context

        institution = self.request.user.institution
        cache_key = f"dashboard_stats_institution_{institution.id}"
        cached_data = cache.get(cache_key)

        if not cached_data:

            all_device_ids_list, _ = Device.get_all(institution, limit=None)
            unassigned_device_ids_list, _ = Device.get_unassigned(institution, limit=None)
            unassigned_ids_set = {d.id for d in unassigned_device_ids_list}
            total_devices = len(all_device_ids_list)

            # Get State Map
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

            # Get Lot Map
            device_id_to_lot_map = {}
            all_device_lots = DeviceLot.objects.filter(
                lot__owner=institution,
                lot__archived=False
            ).select_related('lot')
            for dl in all_device_lots:
                device_id_to_lot_map.setdefault(dl.device_id, []).append(dl.lot)

            # process in Batches
            total_types_counter = Counter()
            assigned_types_counter = Counter()
            unassigned_types_counter = Counter()
            states_breakdown = {}
            lots_breakdown = {}
            batch_size = 500

            for i in range(0, total_devices, batch_size):
                batch_id_objects = all_device_ids_list[i:i + batch_size]
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
                    states_breakdown.setdefault(state_name, {'total': 0, 'types': Counter()})['total'] += 1
                    states_breakdown[state_name]['types'][device_type] += 1

                    if is_assigned:
                        lots_for_device = device_id_to_lot_map.get(d.id, [])
                        for lot in lots_for_device:
                            lots_breakdown.setdefault(lot.pk, {'name': lot.name, 'total': 0, 'types': Counter()})['total'] += 1
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
            lots_summary = sorted(lots_summary, key=lambda x: x['count'], reverse=True)

            unassigned_devices = len(unassigned_ids_set)
            assigned_devices = total_devices - unassigned_devices

            cached_data = {
                'last_updated': timezone.now(),
                'total_devices': total_devices,
                'total_types_summary': total_types_summary,
                'unassigned_devices': unassigned_devices,
                'unassigned_types_summary': unassigned_types_summary,
                'assigned_devices': assigned_devices,
                'assigned_types_summary': assigned_types_summary,
                'lots_summary': lots_summary,
                'states_summary': states_summary,
            }
            cache.set(cache_key, cached_data, timeout=14400)


        final_context = cached_data.copy()
        profile, created = UserProfile.objects.get_or_create(user=self.request.user)

        pinned_lot_pks = set(profile.pinned_lots.values_list('pk', flat=True))
        pinned_state_pks = set(profile.pinned_states.values_list('pk', flat=True))
        has_pinned_lots = bool(pinned_lot_pks)
        has_pinned_states = bool(pinned_state_pks)

        if has_pinned_lots:
            cached_lots_map = {lot['pk']: lot for lot in cached_data['lots_summary']}
            user_lots_summary = []

            all_pinned_lots = Lot.objects.filter(pk__in=pinned_lot_pks)

            for lot in all_pinned_lots:
                if lot.pk in cached_lots_map:
                    user_lots_summary.append(cached_lots_map[lot.pk])
                else:
                    user_lots_summary.append({
                        'pk': lot.pk,
                        'name': lot.name,
                        'count': 0,
                        'types': {}
                    })
            final_context['lots_summary'] = sorted(user_lots_summary, key=lambda x: x['name'])
        else:
            final_context['lots_summary'] = cached_data['lots_summary'][:10]


        if has_pinned_states:
            cached_states_map = {state['state']: state for state in cached_data['states_summary']}
            user_states_summary = []

            all_pinned_states = StateDefinition.objects.filter(pk__in=pinned_state_pks)

            for state_def in all_pinned_states:
                state_name = state_def.state
                if state_name in cached_states_map:
                    # State is pinned AND has devices
                    user_states_summary.append(cached_states_map[state_name])
                else:
                    user_states_summary.append({
                        'state': state_name,
                        'count': 0,
                        'types': {}
                    })
            final_context['states_summary'] = sorted(user_states_summary, key=lambda x: x['state'])
        else:
            final_context['states_summary'] = cached_data['states_summary']

        final_context['has_pinned_lots'] = has_pinned_lots
        final_context['has_pinned_states'] = has_pinned_states

        context.update(final_context)
        return context
