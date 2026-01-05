from django.urls import resolve
from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, Http404
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import PermissionDenied
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic.base import TemplateView
from device.models import Device
from evidence.models import SystemProperty, RootAlias
from lot.models import LotTag
from action.models import StateDefinition
from dashboard.tables import DeviceTable
from django_tables2 import RequestConfig, SingleTableView
from django.utils.dateparse import parse_datetime


class Http403(PermissionDenied):
    status_code = 403
    default_detail = _('Permission denied. User is not authenticated')
    default_code = 'forbidden'

    def __init__(self, details=None, code=None):
        if details is not None:
            self.detail = details or self.default_details
        if code is not None:
            self.code = code or self.default_code


class DashboardView(LoginRequiredMixin):
    login_url = "/login/"
    template_name = "dashboard.html"
    breadcrumb = ""
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
            'path': resolve(self.request.path).url_name,
            'user': self.request.user,
            'lot_tags': lot_tags
        })
        return context

    def get_session_devices(self):
        dev_ids = self.request.session.pop("devices", [])
        user_institution = self.request.user.institution

        prop_device_ids = SystemProperty.objects.filter(
            value__in=dev_ids,
            owner=user_institution
        ).values_list('value', flat=True)

        alias_device_ids = RootAlias.objects.filter(
            root__in=dev_ids,
            owner=user_institution
        ).values_list('root', flat=True)

        all_device_ids = set(prop_device_ids) | set(alias_device_ids)
        self._devices = []

        for x in all_device_ids:
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

    def post(self, request, *args, **kwargs):
        post = dict(self.request.POST)
        url = post.get("url")

        if url:
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return self.configure_table(context)

    def build_table_row(self, device):
        current_state = device.get_current_state()
        return {
            'id': device.pk,
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
        table = DeviceTable(table_data)

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
