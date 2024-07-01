from django.views import View
from django.template.loader import get_template
from django.http import HttpResponse
from django.urls import resolve
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import PermissionDenied
from django.contrib.auth.mixins import LoginRequiredMixin


class Http403(PermissionDenied):
    status_code = 403
    default_detail = _('Permission denied. User is not authenticated')
    default_code = 'forbidden'

    def __init__(self, details=None, code=None):
        if details is not None:
            self.detail = details or self.default_details
        if code is not None:
            self.code = code or self.default_code


class DashboardView(LoginRequiredMixin, View):
    login_url = "/login/"
    template_name = "dashboard.html"

    def get(self, request, *args, **kwargs):

        template = get_template(
            self.template_name,
        ).render()
        return HttpResponse(template)
        
        # response = super().get(request, *args, **kwargs)
        # return response
        
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            # 'title': self.title,
            # 'subtitle': self.subtitle,
            # 'icon': self.icon,
            # 'section': self.section,
            'path': resolve(self.request.path).url_name,
            # 'user': self.request.user,
        })
        return context
