import json
import logging
import re
from urllib.parse import parse_qsl

from tablib import Dataset

from django.db.models import Count
from collections import Counter
from django.utils.translation import gettext_lazy as _
from django.core.cache import cache
from django.contrib import messages
from django.views.generic.edit import FormView
from django.shortcuts import Http404, get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.http import HttpResponse
from dashboard.tables import ProductCacheTable
from dashboard.mixins import DashboardView
from django.views.generic.base import TemplateView

from django_tables2 import RequestConfig
from django_tables2.views import SingleTableMixin
from django_tables2.export.export import TableExport
from django_tables2.export.views import ExportMixin

from action.models import StateDefinition, State
from django.db.models import Q, Subquery, OuterRef

from dashboard.mixins import InventaryMixin, DetailsMixin, DeviceTableMixin, ProductCacheTableMixin
from evidence.models import SystemProperty, RootAlias, UserProperty
from user.models import UserProfile
from evidence.xapian import search
from device.models import Device
from device.product_cache import ProductCache
from lot.models import Lot, LotSubscription, Donor, DeviceLot, DeviceBeneficiary

logger = logging.getLogger('django')

class UnassignedDevicesView(ProductCacheTableMixin, InventaryMixin):
    template_name = "unassigned_devices.html"
    section = _("Inbox")
    title = _("Inbox")
    breadcrumb = [(_('Devices'), reverse_lazy("dashboard:all_device")), (_('Inbox'), None)]

    def get_device_ids(self, offset=0, limit=None):
        institution = self.request.user.institution
        qry = Device.queryset_orm_unassigned(institution)
        # Counted off the same queryset that yields the rows, so the paginator
        # total can never disagree with what the list actually holds.
        count = qry.count()
        qry = self.sorted_roots(qry, institution)
        rows = qry[offset:] if limit is None else qry[offset:offset + limit]
        root_ids = [r["root"] for r in rows]
        return root_ids, count

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # The paginator total is the badge value, so refresh it for free here.
        self.set_unassigned_count(context["count"])
        context["unassigned_count"] = context["count"]
        return context


class AllDevicesView(ProductCacheTableMixin, InventaryMixin):
    template_name = "unassigned_devices.html"
    section = _("All")
    title = _("All Devices")
    breadcrumb = [(_('Devices'), reverse_lazy("dashboard:all_device")), (_('All'), None)]

    def get_device_ids(self, offset=0, limit=None):
        institution = self.request.user.institution
        qry = Device._roots_queryset(institution)
        qry = self.sorted_roots(qry, institution)
        rows = qry[offset:] if limit is None else qry[offset:offset + limit]
        root_ids = [r["root"] for r in rows]
        count = (
            RootAlias.objects.filter(owner=institution)
            .values("root").distinct().count()
        )
        return root_ids, count


class LotDashboardView(ExportMixin, SingleTableMixin, InventaryMixin, DetailsMixin):
    template_name = "unassigned_devices.html"
    section = "dashboard_lot"
    breadcrumb = [(_('Devices'), reverse_lazy("dashboard:all_device")), (_('Devices'), None)]
    paginate_by = 10
    paginate_choices = [10, 20, 50, 100, 0]
    table_class = ProductCacheTable
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

        # Rows are fully populated by get_table_data from the projection read
        # model; no per-row Device construction (and thus no Xapian) here.

        limit = int(self.request.GET.get('limit', self.paginate_by))
        page = int(self.request.GET.get('page', 1))
        search = self.request.GET.get('lquery', '')
        if search:
            count = getattr(self, '_search_count', None)
            if count is None:
                count = len(list(context['table'].rows))
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
            'search': search,
            'query_param': 'lquery',
            'sort': self.request.GET.get('sort', ''),
            'breadcrumb': [
                (_("Lots"), reverse_lazy("dashboard:unassigned")),
                (lot.type.name, reverse_lazy("lot:tags", args=[lot.type.pk])),
                (lot.name, None),
            ],
            'subscripted': subscriptions.first(),
            'is_circuit_manager': is_circuit_manager,
            'is_shop': is_shop,
            'donor': donor,
        })
        return context

    def get_table_data(self):
        search = self.request.GET.get('lquery', '').lower()
        chids = list(self._get_chids_qs())

        # Both paths read the ProductCache read model (no per-device Device
        # construction, and thus no Xapian read/parse per row). Search just
        # narrows the canonical roots before the shared sort + pagination.
        if search:
            device_ids = self._search_roots(chids, search)
            self._search_count = len(device_ids)
        else:
            device_ids = chids
            self._total_count = len(device_ids)

        if not device_ids:
            return []

        rows_by_id, sort_keys = self._build_table_rows(device_ids)

        # Phase 3: sort in Python
        sort_param = self.request.GET.get('sort', '-last_updated')
        reverse = sort_param.startswith('-')
        sort_field = sort_param.lstrip('-')

        def get_sort_val(did):
            keys = sort_keys[did]
            if sort_field in keys:
                return keys[sort_field]
            return rows_by_id[did]['shortid']  # shortid fallback

        none_ids = [did for did in device_ids if get_sort_val(did) is None]
        val_ids  = [did for did in device_ids if get_sort_val(did) is not None]
        sorted_ids = sorted(val_ids, key=get_sort_val, reverse=reverse) + none_ids

        limit = int(self.request.GET.get('limit', self.paginate_by))
        page  = int(self.request.GET.get('page', 1))
        offset = (page - 1) * limit if limit else 0
        page_ids = sorted_ids[offset:offset + limit] if limit else sorted_ids

        return [rows_by_id[did] for did in page_ids]

    def get_table_kwargs(self):
        kwargs = super().get_table_kwargs()
        # Pagination is handled at SQL level; disable django-tables2 pagination
        self.table_pagination = False

        if not self.object.beneficiary_set.exists():
            kwargs['exclude'] = ('status_beneficiary',)

        # Rows are already ordered in get_table_data; mirror the request sort
        # onto the table so the header arrows point at the active column.
        sort = self.request.GET.get('sort', '')
        if sort:
            kwargs['order_by'] = sort

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
        search = self.request.GET.get('lquery', '').lower()
        if search:
            chids = self._search_roots(chids, search)
        return chids

    def _search_roots(self, device_ids, search_query):
        """Filter canonical roots by ``search_query`` against the ProductCache
        read model, matching the same device fields without constructing
        Device objects (no Xapian read/parse per device).

        Whitespace separates terms and a device must match all of them (AND).
        A ``term:field`` token restricts that term to one field; a bare term
        matches any field plus the device's user properties.
        """
        projections, state_by_root, status_by_root = self._batch_device_data(
            device_ids)
        available = DeviceBeneficiary.Status.AVAILABLE.label

        # (value, field) per whitespace-separated term; field is None for a
        # bare term (matches any field + user properties).
        terms = []
        for token in search_query.lower().split():
            value, field = token, None
            if ':' in token:
                value, field = token.rsplit(':', 1)
                field = field.strip()
            value = value.strip()
            if value:
                terms.append((value, field))
        if not terms:
            return list(device_ids)

        # User properties are only consulted when a bare (fieldless) term exists.
        user_props = {}
        if any(field is None for _, field in terms):
            for up in UserProperty.objects.filter(
                owner=self.request.user.institution, device_id__in=device_ids,
                type=UserProperty.Type.USER,
            ).values('device_id', 'key', 'value'):
                user_props.setdefault(up['device_id'], []).extend(
                    [str(up['key']).lower(), str(up['value']).lower()])

        matched = []
        for did in device_ids:
            p = projections.get(did)
            data = p.data if p else {}
            status = status_by_root.get(did)
            fields = {
                'shortid': (p.shortid if p else '').lower(),
                'type': (p.type if p else '').lower(),
                'manufacturer': (p.manufacturer if p else '').lower(),
                'model': (p.model if p else '').lower(),
                'current_state': (state_by_root.get(did) or '').lower(),
                'status_beneficiary': (
                    DeviceBeneficiary.Status(status).label
                    if status is not None else available).lower(),
                'serial': (p.serial if p else '').lower(),
                'cpu': (p.cpu_model if p else '').lower(),
                'total_ram': str(data.get('ram_total', '')).lower(),
            }
            props = user_props.get(did, [])

            def term_matches(value, field):
                if field is not None:
                    val = fields.get(field)
                    return val is not None and value in val
                return (any(value in v for v in fields.values())
                        or any(value in v for v in props))

            if all(term_matches(value, field) for value, field in terms):
                matched.append(did)
        return matched

    def _batch_device_data(self, device_ids):
        """Batch the projection + relational data for ``device_ids`` (canonical
        roots), resolving evidence aliases. Fixed query count, no Xapian.
        Returns three dicts keyed by root: projection rows, current state and
        beneficiary status. Shared by the list view and the export.
        """
        institution = self.request.user.institution

        projections = {
            p.root: p for p in ProductCache.objects.filter(
                owner=institution, root__in=device_ids)
        }

        # alias -> root, plus the full physical-id set, in one query.
        alias_to_root = {}
        alias_ids = set(device_ids)
        for ra in RootAlias.objects.filter(
            owner=institution, root__in=device_ids
        ).values('alias', 'root'):
            alias_to_root[ra['alias']] = ra['root']
            alias_ids.add(ra['alias'])

        # newest evidence uuid per root (across its physical aliases).
        root_latest_uuid = {}
        for sp in SystemProperty.objects.filter(
            owner=institution, value__in=alias_ids
        ).order_by('-created').values('value', 'uuid'):
            root = alias_to_root.get(sp['value'], sp['value'])
            root_latest_uuid.setdefault(root, sp['uuid'])

        # current state per root via its latest uuid.
        uuid_to_root = {uuid: root for root, uuid in root_latest_uuid.items()}
        state_by_root = {}
        for st in State.objects.filter(
            snapshot_uuid__in=root_latest_uuid.values()
        ).order_by('-date').values('snapshot_uuid', 'state'):
            root = uuid_to_root.get(st['snapshot_uuid'])
            if root is not None:
                state_by_root.setdefault(root, st['state'])

        # beneficiary status per root (any physical id may carry the row).
        status_by_root = {}
        for db in DeviceBeneficiary.objects.filter(
            device_id__in=alias_ids,
        ).values('device_id', 'status'):
            root = alias_to_root.get(db['device_id'], db['device_id'])
            if root not in status_by_root or db['status'] > status_by_root[root]:
                status_by_root[root] = db['status']

        return projections, state_by_root, status_by_root

    def _build_table_rows(self, device_ids):
        """Full list-view rows from the projection, keyed by root. Returns
        (rows_by_id, sort_keys); sort_keys holds the raw sortable values
        (datetime / state string / status int) for the Python sort."""
        projections, state_by_root, status_by_root = self._batch_device_data(
            device_ids)

        available = DeviceBeneficiary.Status.AVAILABLE.label
        rows_by_id, sort_keys = {}, {}
        for did in device_ids:
            p = projections.get(did)
            state = state_by_root.get(did)
            status = status_by_root.get(did)
            rows_by_id[did] = {
                'id': did,
                'link_pk': did,
                'shortid': p.shortid if p else did.split(':')[1][:6].upper(),
                'type': p.type if p else '',
                'manufacturer': p.manufacturer if p else '',
                'model': p.model if p else '',
                'cpu': p.cpu_model if p else '',
                'current_state': state or '--',
                'status_beneficiary': (
                    DeviceBeneficiary.Status(status).label
                    if status is not None else available),
                'last_updated': (p.last_updated if p else None) or '--',
            }
            sort_keys[did] = {
                'type': p.type if p else None,
                'manufacturer': p.manufacturer if p else None,
                'model': p.model if p else None,
                'last_updated': p.last_updated if p else None,
                'current_state': state,
                'status_beneficiary': status if status is not None else 0,
            }
        return rows_by_id, sort_keys

    def _export_rows(self, device_ids):
        """Assemble export rows for ``device_ids`` (canonical roots) using the
        ProductCache read model plus batched relational queries. Reads no
        evidence (Xapian): hardware fields come from the projection, the rest
        from Postgres in a fixed number of queries regardless of device count.
        """
        institution = self.request.user.institution
        projections, state_by_root, status_by_root = self._batch_device_data(
            device_ids)

        # user properties per canonical device id.
        user_props = {}
        for up in UserProperty.objects.filter(
            owner=institution, device_id__in=device_ids,
            type=UserProperty.Type.USER,
        ).values('device_id', 'key', 'value'):
            user_props.setdefault(up['device_id'], []).append(
                "({}:{}) ".format(up['key'], up['value']))

        available = DeviceBeneficiary.Status.AVAILABLE.label
        rows = []
        for did in device_ids:
            p = projections.get(did)
            data = p.data if p else {}
            state = state_by_root.get(did)
            status = status_by_root.get(did)
            # openpyxl (xlsx export) rejects tz-aware datetimes, so strip the
            # tzinfo at this export boundary.
            last_updated = p.last_updated if p else None
            if last_updated and timezone.is_aware(last_updated):
                last_updated = timezone.make_naive(last_updated)
            rows.append([
                p.shortid if p else did.split(':')[1][:6].upper(),
                p.type if p else '',
                p.manufacturer if p else '',
                p.model if p else '',
                p.cpu_model if p else '',
                data.get('cpu_cores', ''),
                state or '',
                data.get('ram_total', ''),
                data.get('ram_type', ''),
                data.get('ram_slots', ''),
                data.get('slots_used', ''),
                data.get('drive', ''),
                data.get('gpu_model', ''),
                "".join(user_props.get(did, [])),
                p.serial if p else '',
                last_updated or '',
                DeviceBeneficiary.Status(status).label
                if status is not None else available,
            ])
        return rows

    def create_export(self, export_format):
        if export_format in ('csv', 'xlsx'):
            device_ids = list(self.get_all_device_ids())

            headers = [
                'ID', 'type', 'manufacturer', 'model', 'cpu_model', 'cpu_cores', 'current_state',
                'ram_total', 'ram_type', 'ram_slots', 'slots_used', 'drive', 'gpu_model', 'user_properties','serial', 'last_updated', 'beneficiary_status'
            ]
            data = Dataset(headers=headers)
            for row in self._export_rows(device_ids):
                data.append(row)

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
    breadcrumb = [(_("All Devices"), reverse_lazy("dashboard:all_device")), (_("Search"), None)]
    table_order_by = ()  # override DeviceTable.Meta order_by=("-last_updated",) to preserve relevance order

    def _winning_match_mode(self, request):
        """Return 'best', 'exact' or None: whichever of best_match/exact_match
        is true and appears last in the raw querystring wins over the other."""
        raw_params = parse_qsl(request.META.get("QUERY_STRING", ""), keep_blank_values=True)
        last_key = None
        last_true = False
        for key, value in raw_params:
            if key in ("best_match", "exact_match"):
                last_key = key
                last_true = value.lower() == "true"
        if not last_true:
            return None
        return "best" if last_key == "best_match" else "exact"

    def get(self, request, *args, **kwargs):
        query = request.GET.get("gquery")
        mode = self._winning_match_mode(request) if query else None
        if mode:
            devices, total = self.get_devices(request.user, 0, 1)
            redirect_ok = total >= 1 if mode == "best" else total == 1
            if redirect_ok:
                public = request.GET.get("public", "").lower() == "true"
                url_name = "device:device_web" if public else "device:details"
                pk = devices[0].pk
                if public:
                    # PublicDeviceWebView resolves by literal
                    # SystemProperty.value (no owner), so a bare custom_id
                    # root (RootAlias-only, no backing SystemProperty) would
                    # 404; web_pk needs hids populated to fall back to a
                    # real physical id in that case.
                    devices[0].get_hids()
                    pk = devices[0].web_pk
                return redirect(url_name, pk=pk)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        search_params = self.request.GET.urlencode(),
        search = self.request.GET.get("gquery")
        if search:
            context.update({
                'search_params': search_params,
                'search': search,
                'query_param': 'gquery',
            })

        return context

    def get_devices(self, user, offset, limit):
        query = dict(self.request.GET).get("gquery")

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
        seen = set()
        distinct_page_ids = []
        for pid in page_ids:
            if pid not in seen:
                seen.add(pid)
                distinct_page_ids.append(pid)
        devices = [Device(id=x, owner=user.institution) for x in distinct_page_ids]

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
    breadcrumb = [(_("Dashboard"), reverse_lazy("dashboard:all_device")), (_("Overview"), None)]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if not hasattr(self.request.user, 'institution'):
            context['error'] = 'User is not associated with an institution.'
            return context

        institution = self.request.user.institution

        # fetch User Preferences First
        profile, _ = UserProfile.objects.get_or_create(user=self.request.user)
        pinned_lot_pks = set(profile.pinned_lots.values_list('pk', flat=True))
        pinned_state_pks = set(profile.pinned_states.values_list('pk', flat=True))
        has_pinned_lots = bool(pinned_lot_pks)
        has_pinned_states = bool(pinned_state_pks)

        # fetch all devices from the ProductCache model
        pc_qs = ProductCache.objects.filter(owner=institution)
        device_info = list(pc_qs.values_list('root', 'type'))

        root_to_type = {root: (dtype or 'Unknown') for root, dtype in device_info}
        total_devices = len(device_info)
        all_roots = set(root_to_type.keys())

        #  unassigned devices
        assigned_roots = set(
            DeviceLot.objects.filter(lot__owner=institution)
            .values_list('device_id', flat=True)
        )
        unassigned_ids_set = all_roots - assigned_roots
        # Same set the sidebar badge counts, already computed here.
        self.set_unassigned_count(len(unassigned_ids_set))
        context['unassigned_count'] = len(unassigned_ids_set)

        # Count total, assigned, and unassigned types
        total_types_counter = Counter()
        assigned_types_counter = Counter()
        unassigned_types_counter = Counter()

        for root, dtype in device_info:
            total_types_counter[dtype] += 1
            if root in unassigned_ids_set:
                unassigned_types_counter[dtype] += 1
            else:
                assigned_types_counter[dtype] += 1

        # get states
        # currently everything is tied to an evidence uuid it should be a better way
        sys_props = SystemProperty.objects.filter(owner=institution).order_by('-created').values_list('value', 'uuid')
        root_to_uuid = {}
        for val, uuid in sys_props.iterator(chunk_size=2000):
            if val not in root_to_uuid:
                root_to_uuid[val] = uuid

        states = State.objects.filter(snapshot_uuid__in=root_to_uuid.values()).order_by('-date').values_list('snapshot_uuid', 'state')
        uuid_to_state = {}
        for uuid, state in states.iterator(chunk_size=2000):
            if uuid not in uuid_to_state:
                uuid_to_state[uuid] = state

        # determine states
        target_state_names = None
        if has_pinned_states:
            target_state_names = set(StateDefinition.objects.filter(pk__in=pinned_state_pks).values_list('state', flat=True))

        states_breakdown = {}
        for root, dtype in device_info:
            uuid = root_to_uuid.get(root)
            state_name = uuid_to_state.get(uuid, 'Unknown')

            # if user pinned states, ignore counting devices in non-pinned states
            if target_state_names is not None and state_name not in target_state_names:
                continue

            s_data = states_breakdown.setdefault(state_name, {'total': 0, 'types': Counter()})
            s_data['total'] += 1
            s_data['types'][dtype] += 1

        # ensure pinned states with 0 devices still show up in the dictionary
        if target_state_names is not None:
            for s_name in target_state_names:
                if s_name not in states_breakdown:
                    states_breakdown[s_name] = {'total': 0, 'types': Counter()}

        states_summary = [
            {
                'state': name,
                'count': data['total'],
                'types': dict(data['types'].most_common(3))
            }
            for name, data in states_breakdown.items()
        ]

        if has_pinned_states:
            states_summary.sort(key=lambda x: x['state'])
        else:
            states_summary.sort(key=lambda x: x['count'], reverse=True)

        # get lots
        target_lots_info = {}
        if has_pinned_lots:
            # only care about pinned lots if any
            lots_qs = Lot.objects.filter(pk__in=pinned_lot_pks).values_list('pk', 'name')
            for pk, name in lots_qs:
                target_lots_info[pk] = name
        else:
            # else only top 10 largests lots
            lots_qs = Lot.objects.filter(
                owner=institution, archived=False
            ).annotate(
                d_count=Count('devicelot')
            ).order_by('-d_count')[:10].values_list('pk', 'name')
            for pk, name in lots_qs:
                target_lots_info[pk] = name

        lots_breakdown = {
            pk: {'name': name, 'total': 0, 'types': Counter()}
            for pk, name in target_lots_info.items()
        }

        target_lot_pks = set(target_lots_info.keys())

        if target_lot_pks:
            target_device_lots = DeviceLot.objects.filter(
                lot__pk__in=target_lot_pks
            ).values_list('device_id', 'lot__pk')

            for root, lot_pk in target_device_lots:
                if root in root_to_type:
                    dtype = root_to_type[root]
                    lots_breakdown[lot_pk]['total'] += 1
                    lots_breakdown[lot_pk]['types'][dtype] += 1

        lots_summary = [
            {
                'pk': pk,
                'name': data['name'],
                'count': data['total'],
                'types': dict(data['types'].most_common(3))
            }
            for pk, data in lots_breakdown.items()
        ]

        if has_pinned_lots:
            lots_summary.sort(key=lambda x: x['name'])
        else:
            lots_summary.sort(key=lambda x: x['count'], reverse=True)

        context.update({
            'last_updated': timezone.now(),
            'total_devices': total_devices,
            'total_types_summary': dict(total_types_counter.most_common(4)),
            'unassigned_devices': sum(unassigned_types_counter.values()),
            'unassigned_types_summary': dict(unassigned_types_counter.most_common(3)),
            'assigned_devices': sum(assigned_types_counter.values()),
            'assigned_types_summary': dict(assigned_types_counter.most_common(3)),

            'has_pinned_lots': has_pinned_lots,
            'has_pinned_states': has_pinned_states,
            'lots_summary': lots_summary,
            'states_summary': states_summary,
        })

        return context
