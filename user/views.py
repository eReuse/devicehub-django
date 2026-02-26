from decouple import config
from django.urls import reverse, reverse_lazy
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.utils.translation import gettext_lazy as _
from django.views.generic.base import TemplateView
from dashboard.mixins import DashboardView, Http403
from django.views.generic.edit import (
    FormView,
)

from user.models import User
from user.forms import SettingsForm
from api.models import Token
from django_tables2 import RequestConfig
from django.views.generic import DetailView
from evidence.models import Evidence
from evidence.tables import EvidenceTable
from django.utils.html import format_html

from pathlib import Path

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

# Define exactly which files you want to edit here
EDITABLE_FILES = [
    # Beneficiary Statuses
    ('ben_int_sub', 'beneficiary/interested/subject.txt'),
    ('ben_int_txt', 'beneficiary/interested/email.txt'),
    ('ben_int_html', 'beneficiary/interested/email.html'),
    ('ben_conf_sub', 'beneficiary/confirmed/subject.txt'),
    ('ben_conf_txt', 'beneficiary/confirmed/email.txt'),
    ('ben_conf_html', 'beneficiary/confirmed/email.html'),
    ('ben_deliv_sub', 'beneficiary/delivered/subject.txt'),
    ('ben_deliv_txt', 'beneficiary/delivered/email.txt'),
    ('ben_deliv_html', 'beneficiary/delivered/email.html'),
    ('ben_ret_sub', 'beneficiary/returned/subject.txt'),
    ('ben_ret_txt', 'beneficiary/returned/email.txt'),
    ('ben_ret_html', 'beneficiary/returned/email.html'),
    # Circuit manager
    ('cm_ret_sub', 'circuit_manager/subscription_subject.txt'),
    ('cm_ret_txt', 'circuit_manager/subscription_email.txt'),
    ('cm_ret_html', 'circuit_manager/subscription_email.html'),
    # Donor
    ('donor_sub', 'donor/subject.txt'),
    ('donor_txt', 'donor/email.txt'),
    ('donor_html', 'donor/email.html'),
    # Shop
    ('shop_sub', 'shop/subscription_subject.txt'),
    ('shop_txt', 'shop/subscription_email.txt'),
    ('shop_html', 'shop/subscription_email.html'),
    # Subscriptions
    ('sub_acc_sub', 'subscription/accepted_conditions_beneficiary_subject.txt'),
    ('sub_acc_txt', 'subscription/accepted_conditions_beneficiary_email.txt'),
    ('sub_acc_html', 'subscription/accepted_conditions_beneficiary_email.html'),
    ('sub_con_sub', 'subscription/confirmed_beneficiary_subject.txt'),
    ('sub_con_txt', 'subscription/confirmed_beneficiary_email.txt'),
    ('sub_con_html', 'subscription/confirmed_beneficiary_email.html'),
    ('sub_del_sub', 'subscription/delivered_beneficiary_subject.txt'),
    ('sub_del_txt', 'subscription/delivered_beneficiary_email.txt'),
    ('sub_del_html', 'subscription/delivered_beneficiary_email.html'),
    ('sub_ready_sub', 'subscription/incoming_lot_ready_subject.txt'),
    ('sub_ready_txt', 'subscription/incoming_lot_ready_email.txt'),
    ('sub_ready_html', 'subscription/incoming_lot_ready_email.html'),
    ('sub_int_sub', 'subscription/interested_beneficiary_subject.txt'),
    ('sub_int_txt', 'subscription/interested_beneficiary_email.txt'),
    ('sub_int_html', 'subscription/interested_beneficiary_email.html'),
]

def get_template_path_root():
    return Path(__file__).resolve().parent.parent / "dhemail" / "templates"

class TemplateEditorView(DashboardView, TemplateView):
    template_name = "template-editor.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        files_data = []
        for fid, rel_path in EDITABLE_FILES:
            # Assumes get_template_path logic from before
            full_path = get_template_path_root() / rel_path
            content = full_path.read_text(encoding='utf-8') if full_path.exists() else ""
            files_data.append({'fid': fid, 'path': rel_path, 'content': content})

        ctx['files_data'] = files_data
        return ctx

    def post(self, request, *args, **kwargs):
        rel_path = request.POST.get('rel_path')
        content = request.POST.get('content', '')

        if rel_path:
            full_path = get_template_path_root() / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # Normalize: No ^M, exactly one trailing newline
            clean = content.replace('\r\n', '\n').replace('\r', '\n').rstrip() + '\n'
            full_path.write_text(clean, encoding='utf-8')

            messages.success(request, f"Saved: {rel_path}")
        return redirect('user:template-editor')
