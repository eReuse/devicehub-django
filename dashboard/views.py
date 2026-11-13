from collections import Counter
import csv
from functools import reduce
from io import BytesIO
import json
import logging
import operator
import re
from urllib.parse import parse_qsl

from django.db.models import Count, Q
from django.http import HttpResponse, HttpResponseForbidden, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic.base import TemplateView
from django_tables2.export.views import ExportMixin
from django_tables2.views import SingleTableMixin
from openpyxl import Workbook

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
from evidence.models import RootAlias, SystemProperty, UserProperty
from evidence.xapian import search
from lot.models import DeviceBeneficiary, DeviceLot, Donor, Lot, LotSubscription
from user.models import UserProfile



logger = logging.getLogger('django')



class FilteredProductCacheMixin(ExportMixin, SingleTableMixin, InventaryMixin):
    """
    Shared filtering, sorting, pagination, and streaming export mixin for
    LotDashboardView, AllDevicesView, and UnassignedDevicesView.
    """
    template_name = "unassigned_devices.html"
    paginate_by = 10
    paginate_choices = [10, 20, 50, 100, 0]
    table_class = ProductCacheTable
    export_formats = ['csv', 'xlsx']
    export_name = 'devices_export'
    allow_lot_filter = False

    UNASSIGNED_LOT_TOKEN = "__unassigned__"
    STANDARD_FIELDS = ['type', 'manufacturer', 'model', 'cpu_model']
    EXPORT_CHUNK_SIZE = 1000

    # -------------------------------------------------------------------------
    # 1. Base Scope & Alias Helpers
    # -------------------------------------------------------------------------

    def get_base_chids(self):
        """Override in subclass to return iterable of canonical root IDs for the view."""
        raise NotImplementedError

    def _get_cached_base_chids(self):
        """Cache base device IDs on the view instance so we only query them once per request."""
        if not hasattr(self, '_cached_base_chids'):
            raw = self.get_base_chids()
            # Handle both flat string querysets and `.values("root")` dict querysets
            self._cached_base_chids = [
                r["root"] if isinstance(r, dict) else r for r in raw
            ]
        return self._cached_base_chids

    def _get_state_definitions(self):
        return StateDefinition.objects.filter(
            institution=self.request.user.institution
        ).order_by('order')

    def _expand_aliases(self, root_ids):
        """Map physical aliases back to their canonical root ID in a single query."""
        institution = self.request.user.institution
        root_set = set(root_ids)
        alias_to_root = {}
        alias_ids = set(root_set)

        for ra in RootAlias.objects.filter(owner=institution, root__in=root_set).values('alias', 'root'):
            alias_to_root[ra['alias']] = ra['root']
            alias_ids.add(ra['alias'])

        return alias_to_root, alias_ids

    def _resolve_states_for_roots(self, root_ids):
        """Return `{root_id: latest_state_str}` for the given root IDs."""
        if not root_ids:
            return {}
        institution = self.request.user.institution
        alias_to_root, alias_ids = self._expand_aliases(root_ids)

        # Latest snapshot UUID per canonical root
        root_latest_uuid = {}
        for sp in SystemProperty.objects.filter(
            owner=institution, value__in=alias_ids
        ).order_by('-created').values('value', 'uuid').iterator(chunk_size=2000):
            root = alias_to_root.get(sp['value'], sp['value'])
            root_latest_uuid.setdefault(root, sp['uuid'])

        # Latest state per snapshot UUID
        uuid_to_root = {uuid: root for root, uuid in root_latest_uuid.items()}
        state_by_root = {}
        for st in State.objects.filter(
            snapshot_uuid__in=root_latest_uuid.values()
        ).order_by('-date').values('snapshot_uuid', 'state').iterator(chunk_size=2000):
            root = uuid_to_root.get(st['snapshot_uuid'])
            if root is not None:
                state_by_root.setdefault(root, st['state'])

        return state_by_root

    def _resolve_beneficiary_status_for_roots(self, root_ids):
        """Return `{root_id: highest_beneficiary_status_int}` for the given root IDs."""
        if not root_ids:
            return {}
        alias_to_root, alias_ids = self._expand_aliases(root_ids)

        status_by_root = {}
        for db in DeviceBeneficiary.objects.filter(device_id__in=alias_ids).values('device_id', 'status'):
            root = alias_to_root.get(db['device_id'], db['device_id'])
            if root not in status_by_root or db['status'] > status_by_root[root]:
                status_by_root[root] = db['status']

        return status_by_root

    # -------------------------------------------------------------------------
    # 2. Filtering Pipeline
    # -------------------------------------------------------------------------


    def _has_active_filter_params(self, request_get=None):
        """Return True if any search or filter parameter is present in the URL."""
        if request_get is None:
            request_get = self.request.GET

        if (request_get.get('lquery') or request_get.get('gquery') or '').strip():
            return True

        filter_keys = (
            self.STANDARD_FIELDS
            + list(ProductCache.DATA_FIELDS)
            + ['state', 'up_key', 'up_val', 'device_id', 'lot']
        )
        return any(
            any(v.strip() for v in request_get.getlist(k))
            for k in filter_keys
        )

    def _search_roots(self, base_chids, request_get):
        """Filter `base_chids` using SQL pushdown first, then lightweight memory checks."""
        if not base_chids:
            return []

        # Fast path: if no filters or search query are active, return all base IDs immediately
        if not self._has_active_filter_params(request_get):
            return list(base_chids)

        institution = self.request.user.institution
        candidate_ids = set(base_chids)
        data_fields = list(ProductCache.DATA_FIELDS)

        # 1. Lot Filter (only in AllDevicesView)
        if self.allow_lot_filter:
            f_lots = [v.strip() for v in request_get.getlist('lot') if v.strip()]
            if f_lots:
                lot_op = 'and' if request_get.get('lot_op', 'or').strip().lower() == 'and' else 'or'
                none_label = str(_("None")).strip().lower()
                unassigned_tokens = {self.UNASSIGNED_LOT_TOKEN.lower(), "none", none_label}

                per_lot_sets = []
                all_assigned_cache = None

                for val in f_lots:
                    if val.lower() in unassigned_tokens:
                        if all_assigned_cache is None:
                            all_assigned_cache = set(
                                DeviceLot.objects.filter(lot__owner=institution, device_id__in=candidate_ids)
                                .values_list('device_id', flat=True)
                            )
                        per_lot_sets.append(candidate_ids - all_assigned_cache)
                    else:
                        matched = set(
                            DeviceLot.objects.filter(
                                lot__owner=institution,
                                device_id__in=candidate_ids,
                                lot__name__iexact=val,
                            ).values_list('device_id', flat=True)
                        )
                        per_lot_sets.append(matched)

                if per_lot_sets:
                    if lot_op == 'and':
                        lot_matched = reduce(operator.and_, per_lot_sets)
                    else:
                        lot_matched = reduce(operator.or_, per_lot_sets)

                    candidate_ids &= lot_matched
                    if not candidate_ids:
                        return []
        # 2. Device ID Filter (matches either full root or 6-char shortid)
        f_device_ids = [v.strip().lower() for v in request_get.getlist('device_id') if v.strip()]
        if f_device_ids:
            id_q = reduce(operator.or_, (Q(root__icontains=v) | Q(shortid__icontains=v) for v in f_device_ids))
            candidate_ids &= set(
                ProductCache.objects.filter(owner=institution, root__in=candidate_ids)
                .filter(id_q)
                .values_list('root', flat=True)
            )
            if not candidate_ids:
                return []

        # 3. UserProperty Key & Value Filters
        f_up_keys = [k.strip() for k in request_get.getlist('up_key') if k.strip()]
        if f_up_keys:
            key_q = reduce(operator.or_, (Q(key__icontains=k) for k in f_up_keys))
            candidate_ids &= set(
                UserProperty.objects.filter(
                    owner=institution, device_id__in=candidate_ids, type=UserProperty.Type.USER
                ).filter(key_q).values_list('device_id', flat=True)
            )
            if not candidate_ids:
                return []

        f_up_vals = [v.strip() for v in request_get.getlist('up_val') if v.strip()]
        if f_up_vals:
            val_q = reduce(operator.or_, (Q(value__icontains=v) for v in f_up_vals))
            candidate_ids &= set(
                UserProperty.objects.filter(
                    owner=institution, device_id__in=candidate_ids, type=UserProperty.Type.USER
                ).filter(val_q).values_list('device_id', flat=True)
            )
            if not candidate_ids:
                return []

        # 4. Standard ProductCache Columns (type, manufacturer, model, cpu_model)
        active_std = {
            f: [v.strip() for v in request_get.getlist(f) if v.strip()]
            for f in self.STANDARD_FIELDS
        }
        if any(active_std.values()):
            pc_qs = ProductCache.objects.filter(owner=institution, root__in=candidate_ids)
            for f, vals in active_std.items():
                if vals:
                    pc_qs = pc_qs.filter(reduce(operator.or_, (Q(**{f"{f}__icontains": v}) for v in vals)))
            candidate_ids &= set(pc_qs.values_list('root', flat=True))
            if not candidate_ids:
                return []

        # 5. JSON `data` Fields & Global Search Bar (`lquery`)
        active_data = {
            f: [v.strip().lower() for v in request_get.getlist(f) if v.strip()]
            for f in data_fields
        }
        global_query = (request_get.get('lquery') or request_get.get('gquery') or '').strip().lower()
        has_data_filter = any(active_data.values())

        if has_data_filter or global_query:
            projections = {
                p.root: p for p in ProductCache.objects.filter(
                    owner=institution, root__in=candidate_ids
                ).only('root', 'shortid', 'serial', 'type', 'manufacturer', 'model', 'cpu_model', 'data')
            }
            user_props = {}
            if global_query:
                for up in UserProperty.objects.filter(
                    owner=institution, device_id__in=candidate_ids, type=UserProperty.Type.USER
                ).values('device_id', 'key', 'value'):
                    user_props.setdefault(up['device_id'], []).append(
                        f"{str(up['key']).lower()} {str(up['value']).lower()}"
                    )

            filtered_ids = set()
            for did in candidate_ids:
                p = projections.get(did)
                data = (p.data if p and p.data else {})

                if has_data_filter:
                    if any(
                        vals and not any(v in str(data.get(f, '')).lower() for v in vals)
                        for f, vals in active_data.items()
                    ):
                        continue

                if global_query:
                    p_short = (p.shortid if p else did.split(':')[-1][:6]).lower()
                    searchable = " ".join([
                        (p.manufacturer if p else '') or '',
                        (p.type if p else '') or '',
                        (p.model if p else '') or '',
                        (p.cpu_model if p else '') or '',
                        p_short,
                        (p.serial if p else '') or '',
                        did.lower(),
                        " ".join(user_props.get(did, [])),
                    ]).lower()
                    if global_query not in searchable:
                        continue

                filtered_ids.add(did)

            candidate_ids = filtered_ids
            if not candidate_ids:
                return []

        # 6. State Filter
        f_states = [s.strip().lower() for s in request_get.getlist('state') if s.strip()]
        if f_states:
            state_by_root = self._resolve_states_for_roots(candidate_ids)
            candidate_ids = {
                did for did in candidate_ids
                if (state_by_root.get(did) or '').lower() in f_states
            }

        return list(candidate_ids)

    # -------------------------------------------------------------------------
    # 3. Sorting, Pagination & Table Hydration
    # -------------------------------------------------------------------------

    def _sort_and_paginate_ids(self, matched_ids):
        """Sort matched IDs and return only the slice needed for the current page."""
        if not matched_ids:
            return []

        institution = self.request.user.institution
        sort_param = self.request.GET.get('sort', '-last_updated')
        reverse = sort_param.startswith('-')
        sort_field = sort_param.lstrip('-')

        limit = int(self.request.GET.get('limit', self.paginate_by))
        page = int(self.request.GET.get('page', 1))
        offset = (page - 1) * limit if limit else 0

        if sort_field in ('type', 'manufacturer', 'model', 'last_updated'):
            sort_map = dict(
                ProductCache.objects.filter(owner=institution, root__in=matched_ids)
                .values_list('root', sort_field)
            )
            val_ids = [d for d in matched_ids if sort_map.get(d) is not None]
            none_ids = [d for d in matched_ids if sort_map.get(d) is None]
            sorted_ids = sorted(val_ids, key=lambda d: sort_map[d], reverse=reverse) + none_ids

        elif sort_field == 'current_state':
            state_map = self._resolve_states_for_roots(matched_ids)
            val_ids = [d for d in matched_ids if state_map.get(d)]
            none_ids = [d for d in matched_ids if not state_map.get(d)]
            sorted_ids = sorted(val_ids, key=lambda d: state_map[d].lower(), reverse=reverse) + none_ids

        elif sort_field == 'status_beneficiary':
            status_map = self._resolve_beneficiary_status_for_roots(matched_ids)
            sorted_ids = sorted(matched_ids, key=lambda d: status_map.get(d, 0), reverse=reverse)

        else:
            short_map = dict(
                ProductCache.objects.filter(owner=institution, root__in=matched_ids)
                .values_list('root', 'shortid')
            )
            sorted_ids = sorted(
                matched_ids,
                key=lambda d: short_map.get(d) or d.split(':')[-1][:6].upper(),
                reverse=reverse
            )

        return sorted_ids[offset:offset + limit] if limit else sorted_ids

    def _build_table_rows(self, page_ids):
        """Hydrate row dictionaries strictly for the devices visible on the current page."""
        if not page_ids:
            return []

        institution = self.request.user.institution
        projections = {
            p.root: p for p in ProductCache.objects.filter(owner=institution, root__in=page_ids)
        }
        state_by_root = self._resolve_states_for_roots(page_ids)
        status_by_root = self._resolve_beneficiary_status_for_roots(page_ids)
        available = DeviceBeneficiary.Status.AVAILABLE.label

        rows = []
        for did in page_ids:
            p = projections.get(did)
            state = state_by_root.get(did)
            status = status_by_root.get(did)
            rows.append({
                'id': did,
                'link_pk': did,
                'shortid': p.shortid if p else did.split(':')[-1][:6].upper(),
                'type': p.type if p else '',
                'manufacturer': p.manufacturer if p else '',
                'model': p.model if p else '',
                'cpu': p.cpu_model if p else '',
                'current_state': state or '--',
                'status_beneficiary': (
                    DeviceBeneficiary.Status(status).label if status is not None else available
                ),
                'last_updated': (p.last_updated if p else None) or '--',
            })
        return rows

    def get_table_data(self):
        base_chids = self._get_cached_base_chids()
        matched_ids = self._search_roots(base_chids, self.request.GET)
        self._matched_count = len(matched_ids)

        if not matched_ids:
            return []
        page_ids = self._sort_and_paginate_ids(matched_ids)
        return self._build_table_rows(page_ids)

    def get_all_device_ids(self):
        return self._search_roots(self._get_cached_base_chids(), self.request.GET)

    def get_table_kwargs(self):
        kwargs = super().get_table_kwargs()
        self.table_pagination = False
        kwargs['type_display'] = DeviceType.display_map(self.request.user.institution)

        lot = getattr(self, 'object', None)
        if not lot or not lot.beneficiary_set.exists():
            kwargs['exclude'] = ('status_beneficiary',)

        sort = self.request.GET.get('sort', '')
        if sort:
            kwargs['order_by'] = sort
        return kwargs

    # -------------------------------------------------------------------------
    # 4. Single Unified Context Builder
    # -------------------------------------------------------------------------

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        institution = self.request.user.institution
        limit = int(self.request.GET.get('limit', self.paginate_by))
        page = int(self.request.GET.get('page', 1))

        base_chids = self._get_cached_base_chids()
        base_pc = ProductCache.objects.filter(owner=institution, root__in=base_chids)
        data_fields = list(ProductCache.DATA_FIELDS)

        # Build autocomplete options for standard and JSON fields
        std_options = {}
        for f in self.STANDARD_FIELDS:
            vals = base_pc.exclude(**{f: ''}).exclude(**{f"{f}__isnull": True}).values_list(f, flat=True).distinct()
            if vals:
                std_options[f] = set(vals)

        data_options = {}
        for d in base_pc.exclude(data={}).values_list('data', flat=True).iterator(chunk_size=2000):
            if not d:
                continue
            for k, v in d.items():
                if k in data_fields and v and str(v).strip():
                    data_options.setdefault(k, set()).add(str(v).strip())

        user_props_qs = UserProperty.objects.filter(
            owner=institution, device_id__in=base_chids, type=UserProperty.Type.USER
        )
        up_keys = set(user_props_qs.values_list('key', flat=True).distinct())
        up_vals = set(user_props_qs.values_list('value', flat=True).distinct())

        none_label = str(_("None"))
        lot_options, active_lots = [], []
        lot_op = 'or'

        if self.allow_lot_filter:
            db_lots = list(
                Lot.objects.filter(owner=institution)
                .exclude(name__isnull=True).exclude(name='')
                .order_by('archived', 'name')
                .values_list('name', flat=True)
                .distinct()
            )
            lot_options = [none_label] + [l for l in db_lots if l.lower() != none_label.lower()]

            raw_lots = [l.strip() for l in self.request.GET.getlist('lot') if l.strip()]
            unassigned_tokens = {self.UNASSIGNED_LOT_TOKEN.lower(), "none", none_label.lower()}
            for l_val in raw_lots:
                normalized = none_label if l_val.lower() in unassigned_tokens else l_val
                if normalized not in active_lots:
                    active_lots.append(normalized)

            lot_op = 'and' if self.request.GET.get('lot_op', 'or').strip().lower() == 'and' else 'or'

        filter_blocks = []
        all_options = {**std_options, **data_options}
        for f in self.STANDARD_FIELDS + data_fields:
            opts = all_options.get(f)
            active_vals = [v.strip() for v in self.request.GET.getlist(f) if v.strip()]
            if opts or active_vals:
                filter_blocks.append({
                    'name': f,
                    'title': f.replace('_', ' ').title(),
                    'options': sorted(list(opts)) if opts else [],
                    'active': active_vals,
                })

        # Helper to build chip removal URLs
        def make_remove_url(param_name, val_to_remove):
            qd = self.request.GET.copy()
            qd.pop('page', None)
            if param_name == 'lquery':
                qd.pop('lquery', None)
                qd.pop('gquery', None)
            elif param_name == 'lot':
                unassigned_tokens = {self.UNASSIGNED_LOT_TOKEN.lower(), "none", none_label.lower()}
                target = str(val_to_remove).strip().lower()
                vals = [
                    v for v in qd.getlist('lot')
                    if v.strip() and not (
                        (target in unassigned_tokens and v.strip().lower() in unassigned_tokens)
                        or v.strip().lower() == target
                    )
                ]
                if vals:
                    qd.setlist('lot', vals)
                else:
                    qd.pop('lot', None)
            else:
                vals = [
                    v for v in qd.getlist(param_name)
                    if v.strip() and v.lower() != str(val_to_remove).lower()
                ]
                if vals:
                    qd.setlist(param_name, vals)
                else:
                    qd.pop(param_name, None)
            encoded = qd.urlencode()
            return f"?{encoded}" if encoded else "?"

        search_query = (self.request.GET.get('lquery') or self.request.GET.get('gquery') or '').strip()
        active_states = [s.lower() for s in self.request.GET.getlist('state') if s.strip()]
        active_up_keys = [k.strip() for k in self.request.GET.getlist('up_key') if k.strip()]
        active_up_vals = [v.strip() for v in self.request.GET.getlist('up_val') if v.strip()]
        active_device_ids = [v.strip() for v in self.request.GET.getlist('device_id') if v.strip()]

        # Build unified Active Filters list for the ribbon
        active_filters = []
        if search_query:
            active_filters.append({'category': _('Search'), 'value': search_query, 'remove_url': make_remove_url('lquery', search_query)})
        for v in active_device_ids:
            active_filters.append({'category': _('ID'), 'value': v, 'remove_url': make_remove_url('device_id', v)})

        lot_cat_label = _("Lot (AND)") if (lot_op == 'and' and len(active_lots) > 1) else _("Lot")
        for l_val in active_lots:
            active_filters.append({'category': lot_cat_label, 'value': l_val, 'remove_url': make_remove_url('lot', l_val)})

        for s in active_states:
            active_filters.append({'category': _('State'), 'value': s, 'remove_url': make_remove_url('state', s)})
        for k in active_up_keys:
            active_filters.append({'category': _('Key'), 'value': k, 'remove_url': make_remove_url('up_key', k)})
        for v in active_up_vals:
            active_filters.append({'category': _('Value'), 'value': v, 'remove_url': make_remove_url('up_val', v)})
        for block in filter_blocks:
            for val in block['active']:
                active_filters.append({'category': block['title'], 'value': val, 'remove_url': make_remove_url(block['name'], val)})

        clear_qd = self.request.GET.copy()
        for k in list(clear_qd.keys()):
            if k not in ('limit', 'sort'):
                clear_qd.pop(k, None)
        clear_all_url = f"?{clear_qd.urlencode()}" if clear_qd else "?"

        count = getattr(self, '_matched_count', len(base_chids))
        total_pages = (count + limit - 1) // limit if limit else 1

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

            # Filter UI context
            'show_filter_bar': True,
            'allow_lot_filter': self.allow_lot_filter,
            'unassigned_lot_token': self.UNASSIGNED_LOT_TOKEN,
            'none_lot_label': none_label,
            'lot_op': lot_op,
            'lot_options': lot_options,
            'active_lots': active_lots,
            'active_device_ids': active_device_ids,
            'filter_blocks': filter_blocks,
            'active_states': active_states,
            'up_keys_options': sorted(list(up_keys)),
            'up_vals_options': sorted(list(up_vals)),
            'active_up_keys': active_up_keys,
            'active_up_vals': active_up_vals,
            'lquery': search_query,
            'active_filters': active_filters,
            'active_filter_count': len(active_filters),
            'has_active_filters': bool(active_filters),
            'clear_all_url': clear_all_url,
        })
        return context
    # -------------------------------------------------------------------------
    # 5. Guarded & Streamed Export
    # -------------------------------------------------------------------------

    def can_export(self):
        """Disallow exporting the entire unfiltered system in AllDevicesView."""
        is_unscoped_system_view = self.allow_lot_filter and not getattr(self, 'object', None)
        if is_unscoped_system_view and not self._has_active_filter_params():
            return False
        return True

    def get(self, request, *args, **kwargs):
        export_format = request.GET.get(self.export_trigger_param)
        if export_format in self.export_formats:
            if not self.can_export():
                return HttpResponseForbidden(
                    _("Exporting all system devices without filters is not allowed. Please apply at least one filter first.")
                )
            return self.create_export(export_format)
        return super().get(request, *args, **kwargs)

    def _iter_export_rows(self, device_ids):
        institution = self.request.user.institution
        available = str(DeviceBeneficiary.Status.AVAILABLE.label)

        for i in range(0, len(device_ids), self.EXPORT_CHUNK_SIZE):
            chunk_ids = device_ids[i:i + self.EXPORT_CHUNK_SIZE]
            projections = {
                p.root: p for p in ProductCache.objects.filter(owner=institution, root__in=chunk_ids)
            }
            state_by_root = self._resolve_states_for_roots(chunk_ids)
            status_by_root = self._resolve_beneficiary_status_for_roots(chunk_ids)

            user_props = {}
            for up in UserProperty.objects.filter(
                owner=institution, device_id__in=chunk_ids, type=UserProperty.Type.USER
            ).values('device_id', 'key', 'value'):
                user_props.setdefault(up['device_id'], []).append(f"({up['key']}:{up['value']}) ")

            for did in chunk_ids:
                p = projections.get(did)
                data = p.data if p and p.data else {}
                state = state_by_root.get(did)
                status = status_by_root.get(did)
                last_updated = p.last_updated if p else None
                if last_updated and timezone.is_aware(last_updated):
                    last_updated = timezone.make_naive(last_updated)

                yield [
                    p.shortid if p else did.split(':')[-1][:6].upper(),
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
                    str(DeviceBeneficiary.Status(status).label) if status is not None else available,
                ]

    def get_export_filename(self):
        """
        Dynamically generates a safe filename including the base scope,
        applied filters, and the current date/time.
        """
        lot = getattr(self, 'object', None)
        base_name = f"{lot.name}_lot" if lot and lot.name else self.export_name

        # 1. Sanitize the base name (in case a lot name has spaces or special chars)
        base_name = re.sub(r'[\s/\\,;:|]+', '_', base_name.strip())
        base_name = re.sub(r'[^a-zA-Z0-9\-_]', '', base_name)

        # 2. Get current date (e.g., 2026-11-15)
        date_str = timezone.now().strftime("%Y-%m-%d")

        # 3. Extract and sanitize active filters from the URL
        exclude_params = {getattr(self, 'export_trigger_param', '_export'), 'limit', 'page', 'sort'}
        filter_parts = []

        for key, v_list in self.request.GET.lists():
            if key not in exclude_params:
                for val in v_list:
                    if val.strip():
                        # Clean up values (e.g. "__unassigned__" -> "unassigned", "in stock" -> "in_stock")
                        clean_val = val.strip().replace('__', '')
                        clean_val = re.sub(r'[\s/\\,;:|]+', '_', clean_val)
                        clean_val = re.sub(r'[^a-zA-Z0-9\-_]', '', clean_val)

                        # Shorten keys slightly (e.g. "device_id" -> "deviceid")
                        clean_key = re.sub(r'[^a-zA-Z0-9]', '', key)

                        if clean_val:
                            filter_parts.append(f"{clean_key}-{clean_val}")

        # Join filters and cap the length so the OS doesn't reject extremely long filenames
        filter_str = "_".join(filter_parts)
        if len(filter_str) > 60:
            filter_str = filter_str[:57] + "..."

        # 4. Construct final filename
        if filter_str:
            return f"{base_name}_{filter_str}_{date_str}"
        return f"{base_name}_{date_str}"

    def create_export(self, export_format):
        headers = [
            'ID', 'type', 'manufacturer', 'model', 'cpu_model', 'cpu_cores', 'current_state',
            'ram_total', 'ram_type', 'ram_slots', 'slots_used', 'drive', 'gpu_model',
            'user_properties', 'serial', 'last_updated', 'beneficiary_status'
        ]

        # Use our new dynamic filename generator
        filename = self.get_export_filename()
        device_ids = list(self.get_all_device_ids())

        # 1. Streamed CSV Export (Instant start, near-zero RAM)
        if export_format == 'csv':
            class EchoBuffer:
                def write(self, value):
                    return value

            def csv_stream():
                writer = csv.writer(EchoBuffer())
                yield writer.writerow(headers)
                for row in self._iter_export_rows(device_ids):
                    yield writer.writerow(row)

            response = StreamingHttpResponse(csv_stream(), content_type='text/csv; charset=utf-8')
            response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
            return response

        # 2. Write-Only XLSX Export (Low-memory streaming XML writer)
        if export_format == 'xlsx':
            wb = Workbook(write_only=True)
            ws = wb.create_sheet(title="Devices")
            ws.append(headers)
            for row in self._iter_export_rows(device_ids):
                ws.append(row)

            buffer = BytesIO()
            wb.save(buffer)
            buffer.seek(0)

            return HttpResponse(
                content=buffer.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                headers={'Content-Disposition': f'attachment; filename="{filename}.xlsx"'}
            )

        return super().create_export(export_format)

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
        if not hasattr(self, 'object') or self.object is None:
            self.object = get_object_or_404(self.model, pk=self.kwargs['pk'], owner=self.request.user.institution)
        return self.object.devicelot_set.all().values_list("device_id", flat=True).distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lot = context.get('object') or self.object

        subscriptions = LotSubscription.objects.filter(lot=lot, user=self.request.user)
        is_shop = subscriptions.filter(type=LotSubscription.Type.SHOP).first()
        is_circuit_manager = subscriptions.filter(type=LotSubscription.Type.CIRCUIT_MANAGER).first()
        donor = Donor.objects.filter(lot=lot).first()

        context.update({
            'title': "{} {} - {}".format(_("Lot"), lot.name, _("Products")),
            'lot': lot,
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
