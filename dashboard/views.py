from collections import Counter
import json
import logging
import re
from urllib.parse import parse_qsl

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic.base import TemplateView

from action.models import State, StateDefinition
from dashboard.mixins import DashboardView
from dashboard.mixins import (
    DashboardView,
    DetailsMixin,
    DeviceTableMixin,
    InventaryMixin,
)
from dashboard.tables import ProductCacheTable
from device.models import Device, DeviceType
from device.product_cache import ProductCache
from device.services.exporter import DeviceExportService
from device.services.query_builder import ProductQueryBuilder
from django_tables2.export.views import ExportMixin
from django_tables2.views import SingleTableMixin
from evidence.models import RootAlias, SystemProperty, UserProperty
from evidence.xapian import search
from lot.models import DeviceBeneficiary, DeviceLot, Donor, Lot, LotSubscription
from user.models import UserProfile


logger = logging.getLogger('django')



@login_required
def autocomplete_filter(request, field):
    """HTMX endpoint that returns <option> tags for datalists dynamically."""
    query = request.GET.get(field, '').strip()

    # delay database query until at least 3 chars
    if len(query) < 3:
        return HttpResponse("")

    institution = request.user.institution
    results = []

    if field == 'lot':
        results = Lot.objects.filter(
            owner=institution, name__icontains=query
        ).exclude(name__isnull=True).exclude(name='').values_list('name', flat=True).distinct()[:15]

    elif field == 'up_key':
        results = UserProperty.objects.filter(
            owner=institution, type=UserProperty.Type.USER, key__icontains=query
        ).values_list('key', flat=True).distinct()[:15]

    elif field == 'up_val':
        results = UserProperty.objects.filter(
            owner=institution, type=UserProperty.Type.USER, value__icontains=query
        ).values_list('value', flat=True).distinct()[:15]

    elif field in ProductQueryBuilder.STANDARD_FIELDS:
        results = ProductCache.objects.filter(
            owner=institution, **{f"{field}__icontains": query}
        ).exclude(**{f"{field}": ''}).values_list(field, flat=True).distinct()[:15]

    elif field in ProductCache.DATA_FIELDS:
        results = ProductCache.objects.filter(
            owner=institution, **{f"data__{field}__icontains": query}
        ).values_list(f"data__{field}", flat=True).distinct()[:15]

    html = "".join([f'<option value="{val}">' for val in results if val])
    return HttpResponse(html)


class FilteredProductCacheMixin(ExportMixin, SingleTableMixin, InventaryMixin):
    template_name = "unassigned_devices.html"
    paginate_by = 10
    paginate_choices = [10, 20, 50, 100, 0]
    table_class = ProductCacheTable
    export_formats = ['csv', 'xlsx']
    export_name = 'devices_export'
    allow_lot_filter = False

    def get_base_chids(self):
        raise NotImplementedError

    def _get_cached_base_chids(self):
        if not hasattr(self, '_cached_base_chids'):
            self._cached_base_chids = [
                raw_id["root"] if isinstance(raw_id, dict) else raw_id
                for raw_id in self.get_base_chids()
            ]
        return self._cached_base_chids

    def _get_state_definitions(self):
        return StateDefinition.objects.filter(
            institution=self.request.user.institution
        ).order_by('order')

    def get_query_builder(self):
        if not hasattr(self, '_query_builder'):
            self._query_builder = ProductQueryBuilder(
                institution=self.request.user.institution,
                request_get=self.request.GET,
                allow_lot_filter=self.allow_lot_filter,
            )
        return self._query_builder

    def can_export(self):
        # disallow export of all devices (query with no filters)
        is_unscoped_system_view = self.allow_lot_filter and not getattr(self, 'object', None)
        return not (is_unscoped_system_view and not self.get_query_builder().has_active_filter_params())

    def create_export(self, export_format):
        query_builder = self.get_query_builder()
        device_queryset = query_builder.build_queryset(self._get_cached_base_chids())

        lot = getattr(self, 'object', None)
        base_name = f"{lot.name}_lot" if lot and lot.name else self.export_name

        exporter = DeviceExportService(
            institution=self.request.user.institution,
            device_qs=device_queryset,
            request_get=self.request.GET,
            base_name=base_name,
        )
        return exporter.create_export(export_format)

    def get(self, request, *args, **kwargs):
        export_format = request.GET.get(self.export_trigger_param)

        if export_format in self.export_formats:
            if not self.can_export():
                return HttpResponseForbidden(
                    _("Exporting all system devices without filters is not allowed.")
                )

            device_queryset = self.get_query_builder().build_queryset(self._get_cached_base_chids())
            lot = getattr(self, 'object', None)
            base_name = f"{lot.name}_lot" if (lot and lot.name) else self.export_name

            exporter = DeviceExportService(
                institution=request.user.institution,
                device_qs=device_queryset,
                request_get=request.GET,
                base_name=base_name,
            )
            return exporter.create_export(export_format)

        return super().get(request, *args, **kwargs)

    def _build_table_rows(self, cache_objects):
        available_label = DeviceBeneficiary.Status.AVAILABLE.label
        rows = []

        for pc in cache_objects:
            state = getattr(pc, 'current_state_annotated', None)
            status = getattr(pc, 'beneficiary_status_annotated', None)

            rows.append({
                'id': pc.root,
                'link_pk': pc.root,
                'shortid': pc.shortid or pc.root.split(':')[-1][:6].upper(),
                'type': pc.type or '',
                'manufacturer': pc.manufacturer or '',
                'model': pc.model or '',
                'cpu': pc.cpu_model or '',
                'current_state': state or '--',
                'status_beneficiary': (
                    DeviceBeneficiary.Status(status).label if status is not None else available_label
                ),
                'last_updated': pc.last_updated or '--',
            })

        return rows

    def get_table_data(self):
        limit = int(self.request.GET.get('limit', self.paginate_by))
        page = int(self.request.GET.get('page', 1))
        sort_param = self.request.GET.get('sort', '-last_updated')

        self.page_obj = self.get_query_builder().get_paginated_queryset(
            self._get_cached_base_chids(),
            limit=limit,
            page=page,
            sort_param=sort_param,
        )
        items = getattr(self.page_obj, 'object_list', self.page_obj)
        return self._build_table_rows(items)

    def get_table_kwargs(self):
        kwargs = super().get_table_kwargs()
        self.table_pagination = False
        kwargs['type_display'] = DeviceType.display_map(self.request.user.institution)

        lot = getattr(self, 'object', None)
        if not lot or not lot.beneficiary_set.exists():
            kwargs['exclude'] = ('status_beneficiary',)

        if sort_param := self.request.GET.get('sort', ''):
            kwargs['order_by'] = sort_param

        return kwargs

    def _get_clean_list(self, key, lower=False):
        vals = [v.strip() for v in self.request.GET.getlist(key) if v.strip()]
        return [v.lower() for v in vals] if lower else vals

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query_builder = self.get_query_builder()

        limit = int(self.request.GET.get('limit', self.paginate_by))
        page = int(self.request.GET.get('page', 1))

        # pagination metadata extraction
        page_obj = getattr(self, 'page_obj', None)
        if hasattr(page_obj, 'paginator'):
            count = page_obj.paginator.count
            total_pages = page_obj.paginator.num_pages
        elif page_obj is not None:
            count = page_obj.count()
            total_pages = 1
        else:
            count, total_pages = 0, 1

        none_label = str(_("None"))
        unassigned_tokens = {query_builder.UNASSIGNED_LOT_TOKEN.lower(), "none", none_label.lower()}
        active_lots = []
        lot_op = 'or'

        if self.allow_lot_filter:
            for lot_value in self._get_clean_list('lot'):
                normalized = none_label if lot_value.lower() in unassigned_tokens else lot_value
                if normalized not in active_lots:
                    active_lots.append(normalized)

            if self.request.GET.get('lot_op', 'or').strip().lower() == 'and':
                lot_op = 'and'

        # extract  filters
        all_data_fields = query_builder.STANDARD_FIELDS + list(ProductCache.DATA_FIELDS)
        filter_blocks = [
            {
                'name': field_name,
                'title': field_name.replace('_', ' ').title(),
                'active': active_values,
            }
            for field_name in all_data_fields
            if (active_values := self._get_clean_list(field_name))
        ]

        def make_remove_url(param_name, value_to_remove):
            query_dict = self.request.GET.copy()
            query_dict.pop('page', None)

            if param_name in ('lquery', 'gquery'):
                query_dict.pop('lquery', None)
                query_dict.pop('gquery', None)
            else:
                target = str(value_to_remove).strip().lower()
                is_lot = param_name == 'lot'
                target_is_unassigned = is_lot and target in unassigned_tokens

                retained = []
                for current in query_dict.getlist(param_name):
                    clean_curr = current.strip()
                    if not clean_curr:
                        continue
                    lower_curr = clean_curr.lower()
                    if lower_curr == target or (target_is_unassigned and lower_curr in unassigned_tokens):
                        continue
                    retained.append(clean_curr)

                if retained:
                    query_dict.setlist(param_name, retained)
                else:
                    query_dict.pop(param_name, None)

            encoded = query_dict.urlencode()
            return f"?{encoded}" if encoded else "?"

        search_query = (self.request.GET.get('lquery') or self.request.GET.get('gquery') or '').strip()
        active_states = self._get_clean_list('state', lower=True)
        active_up_keys = self._get_clean_list('up_key')
        active_up_vals = self._get_clean_list('up_val')
        active_device_ids = self._get_clean_list('device_id')

        active_filters = []

        def add_filter_chips(category, param_name, values):
            for val in values:
                active_filters.append({
                    'category': category,
                    'value': val,
                    'remove_url': make_remove_url(param_name, val),
                })

        if search_query:
            add_filter_chips(_('Search'), 'lquery', [search_query])

        lot_label = _("Lot (AND)") if (lot_op == 'and' and len(active_lots) > 1) else _("Lot")
        add_filter_chips(_('ID'), 'device_id', active_device_ids)
        add_filter_chips(lot_label, 'lot', active_lots)
        add_filter_chips(_('State'), 'state', active_states)
        add_filter_chips(_('Key'), 'up_key', active_up_keys)
        add_filter_chips(_('Value'), 'up_val', active_up_vals)

        for block in filter_blocks:
            add_filter_chips(block['title'], block['name'], block['active'])

        # Generate the clear all URL preserving only limit and sort
        clear_query_dict = self.request.GET.copy()
        for key in list(clear_query_dict.keys()):
            if key not in ('limit', 'sort'):
                clear_query_dict.pop(key, None)

        encoded_clear = clear_query_dict.urlencode()
        clear_all_url = f"?{encoded_clear}" if encoded_clear else "?"

        context.update({
            'count': count,
            'page': page,
            'total_pages': total_pages,
            'paginate_choices': self.paginate_choices,
            'state_definitions': self._get_state_definitions(),
            'limit': limit,
            'search': search_query,
            'sort': self.request.GET.get('sort', ''),
            'can_export': self.can_export(),
            'show_filter_bar': True,
            'allow_lot_filter': self.allow_lot_filter,
            'unassigned_lot_token': query_builder.UNASSIGNED_LOT_TOKEN,
            'none_lot_label': none_label,
            'lot_op': lot_op,
            'active_lots': active_lots,
            'active_device_ids': active_device_ids,
            'filter_blocks': filter_blocks,
            'active_states': active_states,
            'active_up_keys': active_up_keys,
            'active_up_vals': active_up_vals,
            'lquery': search_query,
            'active_filters': active_filters,
            'active_filter_count': len(active_filters),
            'has_active_filters': bool(active_filters),
            'clear_all_url': clear_all_url,
        })
        return context


class UnassignedDevicesView(FilteredProductCacheMixin):
    section = _("Inbox")
    title = _("Inbox")
    breadcrumb = [(_('Products'), reverse_lazy("dashboard:all_device")), (_('Inbox'), None)]
    export_name = "inbox_devices"
    allow_lot_filter = False

    def get_base_chids(self):
        return Device.queryset_orm_unassigned(self.request.user.institution)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_total = len(self._get_cached_base_chids())
        self.set_unassigned_count(base_total)
        context["unassigned_count"] = base_total
        return context


class AllDevicesView(FilteredProductCacheMixin):
    section = _("All")
    title = _("All Products")
    breadcrumb = [(_('Products'), reverse_lazy("dashboard:all_device")), (_('All'), None)]
    export_name = "all_devices"
    allow_lot_filter = True

    def get_base_chids(self):
        return Device._roots_queryset(self.request.user.institution)


class LotDashboardView(FilteredProductCacheMixin, DetailsMixin):
    section = "dashboard_lot"
    breadcrumb = [(_('Products'), reverse_lazy("dashboard:all_device")), (_('Products'), None)]
    model = Lot
    export_name = 'lot_devices_export'
    allow_lot_filter = False

    def get_base_chids(self):
        if getattr(self, 'object', None) is None:
            self.object = get_object_or_404(
                self.model, pk=self.kwargs['pk'], owner=self.request.user.institution
            )
        return self.object.devicelot_set.values_list("device_id", flat=True).distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lot = context.get('object') or self.object

        subscriptions = LotSubscription.objects.filter(lot=lot, user=self.request.user)

        context.update({
            'title': f"{_('Lot')} {lot.name} - {_('Products')}",
            'lot': lot,
            'breadcrumb': [
                (_("Lots"), reverse_lazy("dashboard:unassigned")),
                (lot.type.name, reverse_lazy("lot:tags", args=[lot.type.pk])),
                (lot.name, None),
            ],
            'subscripted': subscriptions.first(),
            'is_circuit_manager': subscriptions.filter(type=LotSubscription.Type.CIRCUIT_MANAGER).first(),
            'is_shop': subscriptions.filter(type=LotSubscription.Type.SHOP).first(),
            'donor': Donor.objects.filter(lot=lot).first(),
        })
        return context


class SearchView(DeviceTableMixin, InventaryMixin):
    template_name = "unassigned_devices.html"
    section = _("Search")
    title = _("Search Products")
    breadcrumb = [(_("All Products"), reverse_lazy("dashboard:all_device")), (_("Search"), None)]
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
                url_name = "product:device_web" if public else "product:details"
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
