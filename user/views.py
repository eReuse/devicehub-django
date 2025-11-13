from decouple import config
from django.urls import reverse, reverse_lazy
from django.http import HttpResponse
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.views.generic.base import TemplateView
from dashboard.mixins import DashboardView
from django.views.generic.edit import (
    FormView,
)

from user.models import User, UserProfile
from user.forms import SettingsForm
from user.tables import LotSelectionTable, StateSelectionTable
from api.models import Token
from lot.models import Lot

from action.models import StateDefinition
from django_tables2 import RequestConfig
from django.views.generic import DetailView
from evidence.models import Evidence
from evidence.tables import EvidenceTable
from django.utils.html import format_html


class PanelView(DashboardView, TemplateView):
    template_name = "panel.html"
    title = _("User")
    breadcrumb = "User / Panel"
    subtitle = "User panel"

    
class SettingsView(PanelView, FormView):
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


class UserProfileView(PanelView, DetailView):
        template_name = 'user_profile.html'
        model = User
        title = _("")
        breadcrumb = "User / profile"
        context_object_name = 'profile_user'
        slug_field = 'pk'
        slug_url_kwarg = 'user_id'

        def get_context_data(self, **kwargs):
            if self.object.institution != self.request.user.institution:
                raise Http403

            context = super().get_context_data(**kwargs)
            user = self.object

            ev_queryset= Evidence.get_user_evidences(user)
            evidence_table = EvidenceTable(ev_queryset)
            RequestConfig(self.request, paginate={"per_page": 8}).configure(evidence_table)
            context['ev_table'] = evidence_table

            context['email_display'] = user.email
            if self.request.user != user:
                context['email_display'] = format_html(
                    '<a href="mailto:{}" class="text-decoration-none">{}</a>',
                    user.email,
                    user.email
                )

            context['title'] = f"{user.first_name or user.email}'s Profile"
            return context


class CustomizeDashboardView(DashboardView, TemplateView):
    template_name = 'customize_dashboard.html'
    title = _("Customize Overview")
    breadcrumb = "Overview / Customize"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        institution = self.request.user.institution

        profile, created = UserProfile.objects.get_or_create(user=self.request.user)

        lot_queryset = Lot.objects.filter(owner=institution, archived=False)
        state_queryset = StateDefinition.objects.filter(institution=institution)

        pinned_lot_pks = set(profile.pinned_lots.values_list('pk', flat=True))
        pinned_state_pks = set(profile.pinned_states.values_list('pk', flat=True))

        lots_table = LotSelectionTable(lot_queryset)
        lots_table.checked_pks = pinned_lot_pks
        RequestConfig(self.request).configure(lots_table)

        states_table = StateSelectionTable(state_queryset)
        states_table.checked_pks = pinned_state_pks
        RequestConfig(self.request).configure(states_table)

        context['lots_table'] = lots_table
        context['states_table'] = states_table
        return context

    def post(self, request, *args, **kwargs):
        profile = get_object_or_404(UserProfile, user=request.user)

        pinned_lot_ids = request.POST.getlist("select_lot")
        pinned_state_ids = request.POST.getlist("select_state")

        institution = request.user.institution
        valid_lots = Lot.objects.filter(owner=institution, pk__in=pinned_lot_ids)
        valid_states = StateDefinition.objects.filter(institution=institution, pk__in=pinned_state_ids)

        profile.pinned_lots.set(valid_lots)
        profile.pinned_states.set(valid_states)
        profile.save()

        messages.success(request, _("Your dashboard preferences have been saved!"))
        return redirect('dashboard:overview')
