from decouple import config
from django.urls import reverse, reverse_lazy
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.views.generic.base import TemplateView
from django.shortcuts import get_object_or_404, redirect
from dashboard.mixins import DashboardView
from django_tables2 import SingleTableView
from django.views.generic.edit import (
    CreateView,
    DeleteView,
    UpdateView,
    FormView
)
from user.tables import TokensTable
from user.forms import SettingsForm
from api.models import Token
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


class UserProfileView(DashboardView, DetailView):
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


class TokenView(DashboardView, SingleTableView):
    template_name = "token.html"
    title = _("Credential management")
    section = "Credential"
    subtitle = _('Managament Tokens')
    icon = 'bi bi-key'
    model = Token
    table_class = TokensTable

    def get_queryset(self):
        """
        Override the get_queryset method to filter events based on the user type.
        """
        return Token.objects.filter().order_by("-id")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'tokens': Token.objects.all(),
        })
        return context


class TokenDeleteView(DashboardView, DeleteView):
    model = Token

    def get(self, request, *args, **kwargs):
        self.pk = kwargs['pk']
        self.object = get_object_or_404(self.model, pk=self.pk, owner=self.request.user)
        self.object.delete()

        return redirect('user:tokens')


class TokenNewView(DashboardView, CreateView):
    template_name = "new_token.html"
    title = _("Credential management")
    section = "Credential"
    subtitle = _('New Tokens')
    icon = 'bi bi-key'
    model = Token
    success_url = reverse_lazy('user:tokens')
    fields = (
        "tag",
    )

    def form_valid(self, form):
        form.instance.owner = self.request.user
        form.instance.token = uuid4()
        return super().form_valid(form)


class EditTokenView(DashboardView, UpdateView):
    template_name = "new_token.html"
    title = _("Credential management")
    section = "Credential"
    subtitle = _('New Tokens')
    icon = 'bi bi-key'
    model = Token
    success_url = reverse_lazy('user:tokens')
    fields = (
        "tag",
        "is_active"
    )

    def get_form_kwargs(self):
        pk = self.kwargs.get('pk')
        self.object = get_object_or_404(
            self.model,
            owner=self.request.user,
            pk=pk,
        )
        kwargs = super().get_form_kwargs()
        return kwargs
