from decouple import config
from django.urls import reverse
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.views.generic.base import TemplateView
from dashboard.mixins import DashboardView
from django.views.generic.edit import (
    FormView,
)

from user.forms import SettingsForm
from api.models import Token


class PanelView(DashboardView, TemplateView):
    template_name = "panel.html"
    title = _("User")
    breadcrumb = "User / Panel"
    subtitle = "User panel"

    
class SettingsView(DashboardView, FormView):
    template_name = "settings.html"
    title = _("Download Settings")
    breadcrumb = "user / workbench / settings"
    form_class = SettingsForm

    def form_valid(self, form):
        cleaned_data = form.cleaned_data.copy()
        settings_tmpl = "settings.ini"
        path = reverse("api:new_snapshot")
        cleaned_data['url'] = self.request.build_absolute_uri(path)
        
        if config("LEGACY", False):
            cleaned_data['token'] = config.get('TOKEN_LEGACY', '')
            cleaned_data['url'] = config.get('URL_LEGACY', '')
            settings_tmpl = "settings_legacy.ini"
            
        data = render(self.request, settings_tmpl, cleaned_data)
        response = HttpResponse(data.content, content_type="application/text")
        response['Content-Disposition'] = 'attachment; filename={}'.format("settings.ini")
        return response
    
    def get_form_kwargs(self):
        tokens = Token.objects.filter(owner=self.request.user)
        kwargs = super().get_form_kwargs()
        kwargs['tokens'] = tokens
        return kwargs

class ProfileView(DashboardView):
    template_name = "profile.html"
    subtitle = _('My personal data')
    icon = 'bi bi-person-gear'
    fields = ('first_name', 'last_name', 'email')
    success_url = reverse_lazy('idhub:user_profile')
    model = User

    def get_queryset(self, **kwargs):
        queryset = Membership.objects.select_related('user').filter(
                user=self.request.user)

        return queryset

    def get_object(self):
        return self.request.user

    def get_form(self):
        form = super().get_form()
        return form

    def form_valid(self, form):
        return super().form_valid(form)
        
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'lang': self.request.LANGUAGE_CODE,
        })
        return context

