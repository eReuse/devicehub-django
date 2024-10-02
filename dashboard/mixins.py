from django.urls import resolve
from django.shortcuts import get_object_or_404, redirect, Http404
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import PermissionDenied
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic.base import TemplateView
from device.models import Device
from evidence.models import Annotation
from lot.models import LotTag


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
        context.update({
            'title': self.title,
            'subtitle': self.subtitle,
            'breadcrumb': self.breadcrumb,
            # 'icon': self.icon,
            'section': self.section,
            'path': resolve(self.request.path).url_name,
            'user': self.request.user,
            'lot_tags': LotTag.objects.filter(owner=self.request.user)
        })
        return context

    def get_session_devices(self):
        dev_ids = self.request.session.pop("devices", [])
        
        self._devices = []
        for x in Annotation.objects.filter(value__in=dev_ids).filter(owner=self.request.user).distinct():
            self._devices.append(Device(id=x.value))
        return self._devices


class DetailsMixin(DashboardView, TemplateView):

    def get(self, request, *args, **kwargs):
        self.pk = kwargs['pk']
        self.object = get_object_or_404(self.model, pk=self.pk, owner=self.request.user)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'object': self.object,
        })
        return context


class InventaryMixin(DashboardView, TemplateView):

    def post(self, request, *args, **kwargs):
        dev_ids = dict(self.request.POST).get("devices", [])
        self.request.session["devices"] = dev_ids
        url = self.request.POST.get("url")
        if url:
            try:
                resource = resolve(url)
                if resource and dev_ids:
                    return redirect(url)
            except Exception:
                pass
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        limit = self.request.GET.get("limit", 10)
        page = self.request.GET.get("page", 1)
        if limit:
            try:
                limit = int(limit)
                page = int(page)
            except:
                raise Http404

        offset = (page - 1) * limit
        devices, count = self.get_devices(self.request.user, offset, limit)
        total_pages = (count + limit - 1) // limit

        context.update({
            'devices': devices,
            'count': count,
            "limit": limit,
            "offset": offset,
            "page": page,
            "total_pages": total_pages,
        })
        return context
