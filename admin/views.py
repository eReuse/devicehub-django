from django.utils.translation import gettext_lazy as _
from django.views.generic.base import TemplateView
from dashboard.mixins import DashboardView
from user.models import User


class PanelView(DashboardView, TemplateView):
    template_name = "admin_panel.html"
    title = _("Admin")
    breadcrumb = _("admin") + " /"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context


class UsersView(DashboardView, TemplateView):
    template_name = "admin_users.html"
    title = _("Users")
    breadcrumb = _("admin / Users") + " /"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "users": User.objects.filter()
        })
        return context
