from decouple import config
from django.urls import reverse, reverse_lazy
from django.conf import settings
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

from dhemail.models import InstitutionTemplate


def _template_name(rel_path):
    """'app/templates/foo/bar.txt' → 'foo/bar.txt'"""
    parts = rel_path.split('/', 2)
    if len(parts) == 3 and parts[1] == 'templates':
        return parts[2]
    return rel_path


def _allowed_template_names():
    """Set of valid template_names as defined in EDITABLE_GROUPS."""
    return {_template_name(item[1]) for _, _, files in EDITABLE_GROUPS for item in files}


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

# (tab_id, tab_label, [(fid, rel_path), ...])
# For subscriptions, a 3rd element in the file tuple marks a sub-section header.
EDITABLE_GROUPS = [
    ('ben_interested', 'Ben: Interested', [
        ('ben_int_sub', 'dhemail/templates/beneficiary/interested/subject.txt'),
        ('ben_int_txt', 'dhemail/templates/beneficiary/interested/email.txt'),
        ('ben_int_html', 'dhemail/templates/beneficiary/interested/email.html'),
    ]),
    ('ben_confirmed', 'Ben: Confirmed', [
        ('ben_conf_sub', 'dhemail/templates/beneficiary/confirmed/subject.txt'),
        ('ben_conf_txt', 'dhemail/templates/beneficiary/confirmed/email.txt'),
        ('ben_conf_html', 'dhemail/templates/beneficiary/confirmed/email.html'),
    ]),
    ('ben_delivered', 'Ben: Delivered', [
        ('ben_deliv_sub', 'dhemail/templates/beneficiary/delivered/subject.txt'),
        ('ben_deliv_txt', 'dhemail/templates/beneficiary/delivered/email.txt'),
        ('ben_deliv_html', 'dhemail/templates/beneficiary/delivered/email.html'),
    ]),
    ('ben_returned', 'Ben: Returned', [
        ('ben_ret_sub', 'dhemail/templates/beneficiary/returned/subject.txt'),
        ('ben_ret_txt', 'dhemail/templates/beneficiary/returned/email.txt'),
        ('ben_ret_html', 'dhemail/templates/beneficiary/returned/email.html'),
    ]),
    ('circuit_manager', 'Circuit Manager', [
        ('cm_sub', 'dhemail/templates/circuit_manager/subscription_subject.txt'),
        ('cm_txt', 'dhemail/templates/circuit_manager/subscription_email.txt'),
        ('cm_html', 'dhemail/templates/circuit_manager/subscription_email.html'),
    ]),
    ('donor', 'Donor', [
        ('donor_sub', 'dhemail/templates/donor/subject.txt'),
        ('donor_txt', 'dhemail/templates/donor/email.txt'),
        ('donor_html', 'dhemail/templates/donor/email.html'),
        ('donor_web', 'lot/templates/donor_web_detail.html'),
    ]),
    ('shop', 'Shop', [
        ('shop_sub', 'dhemail/templates/shop/subscription_subject.txt'),
        ('shop_txt', 'dhemail/templates/shop/subscription_email.txt'),
        ('shop_html', 'dhemail/templates/shop/subscription_email.html'),
    ]),
    ('subscriptions', 'Subscriptions', [
        ('sub_acc_sub', 'dhemail/templates/subscription/accepted_conditions_beneficiary_subject.txt', 'Accepted conditions'),
        ('sub_acc_txt', 'dhemail/templates/subscription/accepted_conditions_beneficiary_email.txt'),
        ('sub_acc_html', 'dhemail/templates/subscription/accepted_conditions_beneficiary_email.html'),
        ('sub_con_sub', 'dhemail/templates/subscription/confirmed_beneficiary_subject.txt', 'Confirmed'),
        ('sub_con_txt', 'dhemail/templates/subscription/confirmed_beneficiary_email.txt'),
        ('sub_con_html', 'dhemail/templates/subscription/confirmed_beneficiary_email.html'),
        ('sub_del_sub', 'dhemail/templates/subscription/delivered_beneficiary_subject.txt', 'Delivered'),
        ('sub_del_txt', 'dhemail/templates/subscription/delivered_beneficiary_email.txt'),
        ('sub_del_html', 'dhemail/templates/subscription/delivered_beneficiary_email.html'),
        ('sub_ready_sub', 'dhemail/templates/subscription/incoming_lot_ready_subject.txt', 'Lot ready'),
        ('sub_ready_txt', 'dhemail/templates/subscription/incoming_lot_ready_email.txt'),
        ('sub_ready_html', 'dhemail/templates/subscription/incoming_lot_ready_email.html'),
        ('sub_int_sub', 'dhemail/templates/subscription/interested_beneficiary_subject.txt', 'Interested'),
        ('sub_int_txt', 'dhemail/templates/subscription/interested_beneficiary_email.txt'),
        ('sub_int_html', 'dhemail/templates/subscription/interested_beneficiary_email.html'),
    ]),
    ('agreement', 'Agreement', [
        ('ben_agree', 'lot/templates/beneficiary_agreement_detail.html'),
    ]),
]


class TemplateEditorView(DashboardView, TemplateView):
    template_name = "template-editor.html"
    title = _("Template Editor")
    breadcrumb = "User / Template Editor"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if not (request.user.is_admin or request.user.is_shop):
            raise Http403
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        group_id = self.kwargs.get('group_id', EDITABLE_GROUPS[0][0])

        # Nav: all groups with active flag
        nav = [{'id': gid, 'label': glabel, 'active': gid == group_id}
               for gid, glabel, _ in EDITABLE_GROUPS]

        # Files for the active group
        institution = self.request.user.institution
        files_data = []
        for gid, glabel, files in EDITABLE_GROUPS:
            if gid == group_id:
                for item in files:
                    fid, rel_path = item[0], item[1]
                    section = item[2] if len(item) > 2 else None
                    tmpl_name = _template_name(rel_path)
                    tmpl = InstitutionTemplate.objects.filter(
                        institution=institution,
                        template_name=tmpl_name,
                    ).first()

                    if tmpl:
                        content = tmpl.content
                    else:
                        full_path = settings.BASE_DIR / rel_path
                        content = full_path.read_text(encoding='utf-8') if full_path.exists() else ""

                    files_data.append({
                        'fid': fid,
                        'path': rel_path,
                        'content': content,
                        'section': section,
                    })
                break

        ctx['nav'] = nav
        ctx['files_data'] = files_data
        ctx['group_id'] = group_id
        return ctx

    def post(self, request, *args, **kwargs):
        rel_path = request.POST.get('rel_path')
        content = request.POST.get('content', '')
        group_id = self.kwargs.get('group_id', EDITABLE_GROUPS[0][0])

        if rel_path:
            tmpl_name = _template_name(rel_path)
            if tmpl_name not in _allowed_template_names():
                messages.error(request, "Invalid template path.")
                return redirect(reverse('user:template-editor', kwargs={'group_id': group_id}))
            clean = content.replace('\r\n', '\n').replace('\r', '\n').rstrip() + '\n'
            InstitutionTemplate.objects.update_or_create(
                institution=request.user.institution,
                template_name=tmpl_name,
                defaults={'content': clean},
            )
            messages.success(request, f"Saved: {rel_path}")

        return redirect(reverse('user:template-editor', kwargs={'group_id': group_id}))
