from django.utils.translation import gettext_lazy as _
from django.views.generic.base import TemplateView
from dashboard.mixins import DashboardView


class PanelView(DashboardView, TemplateView):
    template_name = "panel.html"
    title = _("User")
    breadcrumb = "User / Panel"
    subtitle = "User panel"
