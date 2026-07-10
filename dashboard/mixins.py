from django.urls import resolve
from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, Http404
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import PermissionDenied
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic.base import TemplateView
from device.models import Device
from device.product_cache import ProductCache
from evidence.models import SystemProperty, RootAlias
from lot.models import LotTag
from action.models import StateDefinition, State
from dashboard.tables import DeviceTable, AllDevicesTable
from django_tables2 import RequestConfig, SingleTableView
from django.utils.dateparse import parse_datetime
from django.db.models import F, Subquery, OuterRef


class Http403(PermissionDenied):
    status_code = 403
    default_detail = _('Permission denied. User is not authenticated')
    default_code = 'forbidden'

    def __init__(self, details=None, code=None):
        if details is not None:
            self.detail = details or self.default_detail
        if code is not None:
            self.code = code or self.default_code


class DashboardView(LoginRequiredMixin):
    login_url = "/login/"
    template_name = "dashboard.html"
    breadcrumb = None # Tuple of string and link. Link can be None
    title = ""
    subtitle = ""
    section = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lot_tags = LotTag.objects.filter(
            owner=self.request.user.institution,
        ).order_by('order')
        context.update({
            "commit_id": settings.COMMIT,
            'title': self.title,
            'subtitle': self.subtitle,
            'breadcrumb': self.breadcrumb,
            # 'icon': self.icon,
            'section': self.section,
            'path': resolve(self.request.path).view_name,
            'user': self.request.user,
            'lot_tags': lot_tags
        })
        return context

    def get_session_devices(self):
        dev_ids = self.request.session.pop("devices", [])

        self._devices = []

        custom_ids = [d for d in dev_ids if d.startswith("custom_id:")]
        regular_ids = [d for d in dev_ids if not d.startswith("custom_id:")]

        if custom_ids:
            root_aliases = RootAlias.objects.filter(
                root__in=custom_ids,
                owner=self.request.user.institution
            ).order_by("-updated")
            seen_roots = set()
            for ra in root_aliases:
                if ra.root not in seen_roots:
                    seen_roots.add(ra.root)
                    regular_ids.append(ra.alias)

        dev_ids_list = SystemProperty.objects.filter(value__in=regular_ids)
        dev_org = dev_ids_list.filter(owner=self.request.user.institution)
        dev_org_set = set(x.value for x in dev_org)
        for x in dev_org_set:
            self._devices.append(Device(id=x))
        return self._devices


class DetailsMixin(DashboardView, TemplateView):

    def get(self, request, *args, **kwargs):
        self.pk = kwargs['pk']
        self.object = get_object_or_404(
            self.model,
            pk=self.pk,
            owner=self.request.user.institution
        )
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'object': self.object,
        })
        return context


class InventaryMixin(DashboardView, TemplateView):

    def get_all_device_ids(self):
        """Override in view subclasses to return all device IDs for the current context."""
        return []

    def post(self, request, *args, **kwargs):
        post = dict(self.request.POST)
        url = post.get("url")

        if url:
            select_all_pages = post.get("select_all_pages", ["false"])[0].lower() == "true"

            if select_all_pages:
                all_ids = self.get_all_device_ids()
                self.request.session["devices"] = all_ids
            else:
                dev_ids = post.get("devices", [])
                self.request.session["devices"] = dev_ids

            try:
                resource = resolve(url[0])
                if resource:
                    return redirect(url[0])
            except Exception:
                pass
        return super().get(request, *args, **kwargs)

#    def get_context_data(self, **kwargs):
#         #TODO: pagination for devices table is done on DeviceTableMixin
#         context = super().get_context_data(**kwargs)
#         limit = self.request.GET.get("limit")
#         page = self.request.GET.get("page")
#         try:
#             limit = int(limit)
#             page = int(page)
#             if page < 1:
#                 page = 1
#             if limit < 1:
#                 limit = 10
#         except:
#             limit = 10
#             page = 1

#         offset = (page - 1) * limit
#         devices, count = self.get_devices(self.request.user, offset, limit)
#         total_pages = (count + limit - 1) // limit

#         context.update({
#             'devices': devices,
#             'count': count,
#             "limit": limit,
#             "offset": offset,
#             "page": page,
#             "total_pages": total_pages,
#         })
#         return context


class DeviceTableMixin():
    """Mixin to handle django-tables2 dict-based tables for Devices"""
    paginate_by = 10
    paginate_choices = [10, 20, 50, 100, 0]
    table_order_by = None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return self.configure_table(context)

    def build_table_row(self, device):
        current_state = device.get_current_state()

        return {
            'id': device.pk,
            'link_pk': device.link_pk,
            'shortid': device.shortid,
            'type': device.type,
            'manufacturer': getattr(device, 'manufacturer', ''),
            'model': getattr(device, 'model', ''),
            'version': getattr(device, 'version', ''),
            'cpu': getattr(device, 'cpu', ''),
            'current_state': current_state.state if current_state else '--',
            'status_beneficiary': getattr(device,'status_beneficiary', ''),
            'last_updated': parse_datetime(device.updated) if device.updated else "--"
        }

    def build_table_data(self, devices):
        return [self.build_table_row(device) for device in devices]

    def get_devices(self, user, offset=0, limit=None):
        raise NotImplementedError

    def configure_table(self, context):
        """Configure and add table to context"""
        limit = int(self.request.GET.get('limit', self.paginate_by))
        page = int(self.request.GET.get('page', 1))
        offset = (page - 1) * limit

        devices, count = self.get_devices(self.request.user, offset, limit)
        total_pages = (count + limit - 1) // limit if limit != 0 else 1

        table_data = self.build_table_data(devices)
        kwargs = {'exclude': ('status_beneficiary',)}
        if self.table_order_by is not None:
            kwargs['order_by'] = self.table_order_by
        table = DeviceTable(table_data, **kwargs)
        if limit != 0:
            RequestConfig(self.request, paginate={'page': page, 'per_page': limit}).configure(table)
        else:
            RequestConfig(self.request, paginate=False).configure(table)

        state_definitions = StateDefinition.objects.filter(
            institution=self.request.user.institution
        ).order_by('order')

        context.update({
            'table': table,
            'count': count,
            'limit': limit,
            'page': page,
            'total_pages': total_pages,
            'paginate_choices': self.paginate_choices,
            "state_definitions": state_definitions
        })
        return context


class ProductCacheTableMixin():
    """Device list table backed by the ProductCache read model.

    Same column structure as the lot table (LotDashboardView) but for the
    All Devices / Inbox lists: rows come from ProductCache plus a fixed
    number of batched relational queries for current_state, with no per-device
    Device construction (and thus no Xapian read/parse per row). Subclasses
    implement get_device_ids() to pick which canonical roots, in what order,
    and the page slice. The beneficiary column is lot-scoped, so it is excluded
    here (these lists are not bound to a single lot).
    """
    paginate_by = 10
    paginate_choices = [10, 20, 50, 100, 0]
    table_order_by = None

    # ?sort= field -> ProductCache column used to order at the DB level.
    # Fields not listed here keep the default -latest order.
    SORTABLE_FIELDS = {
        "shortid": "shortid",
        "type": "type",
        "manufacturer": "manufacturer",
        "model": "model",
        "last_updated": "last_updated",
    }

    def get_device_ids(self, offset=0, limit=None):
        """Return (root_ids_page, total_count). Override in subclasses."""
        raise NotImplementedError

    def get_all_device_ids(self):
        root_ids, _ = self.get_device_ids(offset=0, limit=None)
        return list(root_ids)

    def sorted_roots(self, qry, institution):
        """Reorder a roots queryset by the user's ``?sort=`` request.

        ``qry`` yields dicts grouped by ``root`` (default order -latest). When
        the sort field maps to a ProductCache column the default order is
        replaced by that column via subquery; roots without a projection row
        sort last and ``root`` breaks ties for a stable page slice. An empty or
        unknown sort field keeps the default order.
        """
        sort_param = self.request.GET.get("sort", "")
        column = self.SORTABLE_FIELDS.get(sort_param.lstrip("-"))
        if not column:
            return qry
        proj = ProductCache.objects.filter(
            owner=institution, root=OuterRef("root"))
        qry = qry.annotate(_sortcol=Subquery(proj.values(column)[:1]))
        col = F("_sortcol")
        order = (col.desc(nulls_last=True) if sort_param.startswith("-")
                 else col.asc(nulls_last=True))
        return qry.order_by(order, "root")

    def _batch_product_cache_state(self, root_ids):
        """Batch the projection rows and current state for ``root_ids``
        (canonical roots) in a fixed number of queries, resolving evidence
        aliases. No Xapian. Returns (projections_by_root, state_by_root)."""
        institution = self.request.user.institution

        projections = {
            p.root: p for p in ProductCache.objects.filter(
                owner=institution, root__in=root_ids)
        }

        # alias -> root, plus the full physical-id set, in one query.
        alias_to_root = {}
        alias_ids = set(root_ids)
        for ra in RootAlias.objects.filter(
            owner=institution, root__in=root_ids
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

        return projections, state_by_root

    def build_product_cache_rows(self, root_ids):
        projections, state_by_root = self._batch_product_cache_state(root_ids)
        rows = []
        for did in root_ids:
            p = projections.get(did)
            state = state_by_root.get(did)
            rows.append({
                'id': did,
                'link_pk': did,
                'shortid': p.shortid if p else did.split(':')[1][:6].upper(),
                'type': p.type if p else '',
                'manufacturer': p.manufacturer if p else '',
                'model': p.model if p else '',
                'cpu': p.cpu_model if p else '',
                'current_state': state or '--',
                'last_updated': (p.last_updated if p else None) or '--',
            })
        return rows

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        limit = int(self.request.GET.get('limit', self.paginate_by))
        page = int(self.request.GET.get('page', 1))
        offset = (page - 1) * limit if limit != 0 else 0

        root_ids, count = self.get_device_ids(offset, limit if limit != 0 else None)
        total_pages = (count + limit - 1) // limit if limit != 0 else 1

        table_data = self.build_product_cache_rows(list(root_ids))
        table_kwargs = {'exclude': ('status_beneficiary',)}
        # The page slice is already ordered at the DB level; mirror the request
        # sort onto the table so the header arrows reflect the active column.
        order_by = self.request.GET.get('sort', '') or self.table_order_by
        if order_by:
            table_kwargs['order_by'] = order_by
        table = AllDevicesTable(table_data, **table_kwargs)
        if limit != 0:
            RequestConfig(self.request, paginate={'page': page, 'per_page': limit}).configure(table)
        else:
            RequestConfig(self.request, paginate=False).configure(table)

        state_definitions = StateDefinition.objects.filter(
            institution=self.request.user.institution
        ).order_by('order')

        context.update({
            'table': table,
            'count': count,
            'limit': limit,
            'page': page,
            'total_pages': total_pages,
            'paginate_choices': self.paginate_choices,
            "state_definitions": state_definitions,
            'sort': self.request.GET.get('sort', ''),
        })
        return context
