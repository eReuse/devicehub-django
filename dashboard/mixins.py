from django.urls import resolve
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import PermissionDenied
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic.base import TemplateView


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
        })
        return context


class DetailsMixin(DashboardView, TemplateView):

    def get(self, request, *args, **kwargs):
        self.pk = kwargs['pk']
        self.object = get_object_or_404(self.model, pk=self.pk)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'object': self.object,
        })
        return context
