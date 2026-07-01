import uuid
from django_tables2 import SingleTableView
from smtplib import SMTPException
from django.contrib import messages
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, redirect, Http404
from django.utils.translation import gettext_lazy as _
from django.contrib.messages.views import SuccessMessageMixin
from django.views.generic.base import TemplateView, ContextMixin
from django.views.generic.edit import (
    CreateView,
    UpdateView,
    DeleteView,
)
from evidence.models import CredentialProperty
from openlocationcode import openlocationcode as olc
from django.db import IntegrityError,   transaction
from dashboard.mixins import DashboardView, Http403
from admin.forms import InstitutionDPPSettingsForm, InstitutionLabelSettingsForm, OrderingStateForm, InstitutionLabelSettings, InstitutionDPPSettings, InstitutionForm, FacilityClaimFormSet
from user.models import User, Institution, InstitutionDPPSettings, InstitutionLabelSettings
from admin.email import NotifyActivateUserByEmail
from admin.tables import UserTable
from action.models import StateDefinition
from lot.models import LotTag
from evidence.services import CredentialService

from django.views import View


class AdminView(DashboardView):
    def get(self, *args, **kwargs):
        response = super().get(*args, **kwargs)
        if not self.request.user.is_admin:
            raise Http403

        return response

class PanelView(AdminView, TemplateView):
    template_name = "admin_panel.html"
    title = _("Admin")
    breadcrumb = [(_("admin"), None)]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context


class UsersView(AdminView, SingleTableView):
    template_name = "admin_users.html"
    title = _("Users")
    breadcrumb = [(_("Admin"), reverse_lazy("admin:panel")), (_("Users"), None)]
    table_class = UserTable

    def get_queryset(self):
        return User.objects.filter(institution=self.request.user.institution)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context


class CreateUserView(AdminView, NotifyActivateUserByEmail, CreateView):
    template_name = "user.html"
    title = _("User")
    breadcrumb = [(_("Admin"), reverse_lazy("admin:panel")), (_("Users"), reverse_lazy("admin:users")), (_("New user"), None)]
    success_url = reverse_lazy('admin:users')
    model = User
    fields = (
        "email",
        "password",
        "is_admin",
    )

    def form_valid(self, form):
        form.instance.institution = self.request.user.institution
        form.instance.set_password(form.instance.password)
        response = super().form_valid(form)

        try:
            self.send_email(form.instance)
        except SMTPException as e:
            messages.error(self.request, e)

        return response


class DeleteUserView(AdminView, DeleteView):
    template_name = "delete_user.html"
    title = _("Delete user")
    breadcrumb = [(_("Admin"), reverse_lazy("admin:panel")), (_("Users"), reverse_lazy("admin:users")), (_("Delete user"), None)]
    success_url = reverse_lazy('admin:users')
    model = User
    fields = (
        "email",
        "password",
        "is_admin",
    )

    def form_valid(self, form):
        response = super().form_valid(form)
        return response


class EditUserView(AdminView, UpdateView):
    template_name = "user.html"
    title = _("Edit user")
    breadcrumb = [(_("Admin"), reverse_lazy("admin:panel")), (_("Users"), reverse_lazy("admin:users")), (_("Edit user"), None)]
    success_url = reverse_lazy('admin:users')
    model = User
    fields = (
        "email",
        "is_admin",
    )

    def get_form_kwargs(self):
        pk = self.kwargs.get('pk')
        self.object = get_object_or_404(self.model, pk=pk, institution=self.request.user.institution)
        #self.object.set_password(self.object.password)
        kwargs = super().get_form_kwargs()
        return kwargs


class LotTagPanelView(AdminView, TemplateView):
    template_name = "lot_tag_panel.html"
    title = _("Lot Groups Panel")
    breadcrumb = [(_("Admin"), reverse_lazy("admin:panel")), (_("Lot Groups"), None)]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lot_tags = LotTag.objects.filter(
            owner=self.request.user.institution
        ).order_by('order')
        context.update({"lot_tags_edit": lot_tags})
        return context


class AddLotTagView(AdminView, CreateView):
    template_name = "lot_tag_panel.html"
    title = _("New lot group Definition")
    breadcrumb = [(_("Admin"), reverse_lazy("admin:panel")), (_("Lot Groups"), reverse_lazy("admin:tag_panel")), (_("New lot tag"), None)]
    success_url = reverse_lazy('admin:tag_panel')
    model = LotTag
    fields = ('name',)

    def form_valid(self, form):
        form.instance.owner = self.request.user.institution
        form.instance.user = self.request.user
        name = form.instance.name
        if LotTag.objects.filter(name=name).first():
            msg = _(f"The name '{name}' exist.")
            messages.error(self.request, msg)
            return redirect(self.success_url)

        response = super().form_valid(form)
        messages.success(self.request, _("Lot Group successfully added."))
        return response


class DeleteLotTagView(AdminView, DeleteView):
    model = LotTag
    success_url = reverse_lazy('admin:tag_panel')

    def post(self, request, *args, **kwargs):
        pk = kwargs.get('pk')
        self.object = get_object_or_404(
            self.model,
            owner=self.request.user.institution,
            pk=pk
        )

        if self.object.lot_set.first():
            msg = _('This group have lots. Impossible to delete.')
            messages.warning(self.request, msg)
            return redirect(reverse_lazy('admin:tag_panel'))

        if self.object.inbox:
            msg = f"The lot group '{self.object.name}'"
            msg += " is INBOX, so it cannot be deleted, only renamed."
            messages.error(self.request, msg)
            return redirect(self.success_url)

        response = super().delete(request, *args, **kwargs)
        msg = _('Lot Group has been deleted.')
        messages.success(self.request, msg)
        return response


class UpdateLotTagView(AdminView, UpdateView):
    model = LotTag
    template_name = 'lot_tag_panel.html'
    fields = ['name']
    success_url = reverse_lazy('admin:tag_panel')

    def get_form_kwargs(self):
        pk = self.kwargs.get('pk')
        self.object = get_object_or_404(
            self.model,
            owner=self.request.user.institution,
            pk=pk
        )
        return super().get_form_kwargs()

    def form_valid(self, form):
        name = form.instance.name
        if LotTag.objects.filter(name=name).first():
            msg = _(f"The name '{name}' exist.")
            messages.error(self.request, msg)
            return redirect(self.success_url)

        response = super().form_valid(form)
        msg = _("Lot Group updated successfully.")
        messages.success(self.request, msg)
        return response


class UpdateLotTagOrderView(AdminView, TemplateView):
    success_url = reverse_lazy('admin:tag_panel')

    def post(self, request, *args, **kwargs):
        form = OrderingStateForm(request.POST)

        if form.is_valid():
            ordered_ids = form.cleaned_data["ordering"].split(',')

            with transaction.atomic():
                current_order = 2
                for lookup_id in ordered_ids:
                    lot_tag = LotTag.objects.get(id=lookup_id)

                    if lookup_id != '1':  # skip the inbox lot
                        lot_tag.order = current_order
                        current_order += 1
                    else:
                        #just make sure order is one
                        lot_tag.order = 1

                    lot_tag.save()

            messages.success(self.request, _("Order changed successfully."))
            return redirect(self.success_url)
        else:
            return Http404


class InstitutionView(AdminView, UpdateView):
    template_name = "institution.html"
    title = _("Edit institution")
    breadcrumb = [(_("Admin"), reverse_lazy("admin:panel")), (_("Edit Institution"), None)]
    section = "admin"
    subtitle = _('Edit your institution settings')
    model = Institution
    success_url = reverse_lazy('admin:panel')
    form_class = InstitutionForm

    def get_object(self, queryset=None):
        return self.request.user.institution

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if self.request.POST:
            context['claim_formset'] = FacilityClaimFormSet(
                self.request.POST,
                instance=self.object,
                prefix='claims'
            )
        else:
            context['claim_formset'] = FacilityClaimFormSet(
                instance=self.object,
                prefix='claims'
            )
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        claim_formset = context['claim_formset']

        if claim_formset.is_valid():
            self.object = form.save()

            claim_formset.instance = self.object
            claim_formset.save()

            messages.success(self.request, _("Institution information and claims updated successfully."))
            return super().form_valid(form)
        else:
            return self.form_invalid(form)

    def form_invalid(self, form):
        messages.error(self.request, _("Please correct the errors below."))
        return self.render_to_response(self.get_context_data(form=form))


class InstitutionConfigView(AdminView, UpdateView):
    template_name = "dpp_settings.html"
    model = InstitutionDPPSettings
    form_class = InstitutionDPPSettingsForm
    title = _("Configuration & Signing")
    subtitle = _("Manage technical settings and signing credentials")
    success_url = reverse_lazy('admin:panel')

    def form_valid(self, form):
        messages.success(self.request, _("Configuration updated successfully."))
        return super().form_valid(form)

    def get_object(self, queryset=None):
        institution = self.request.user.institution
        obj, created = InstitutionDPPSettings.objects.get_or_create(institution=institution)
        return obj


class StateDefinitionContextMixin(ContextMixin):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "state_definitions": StateDefinition.objects.filter(institution=self.request.user.institution).order_by('order'),
            "help_text": _('State definitions are the custom finite states that a device can be in.'),
        })
        return context


class StatesPanelView(AdminView, StateDefinitionContextMixin, TemplateView):
    template_name = "states_panel.html"
    title = _("States Panel")
    breadcrumb = [(_("Admin"), reverse_lazy("admin:panel")), (_("States"), None)]


class AddStateDefinitionView(AdminView, StateDefinitionContextMixin, CreateView):
    template_name = "states_panel.html"
    title = _("New State Definition")
    breadcrumb = [(_("Admin"), reverse_lazy("admin:panel")), (_("States"), reverse_lazy("admin:states_panel")), (_("New state"), None)]
    success_url = reverse_lazy('admin:states_panel')
    model = StateDefinition
    fields = ('state',)

    def form_valid(self, form):
        form.instance.institution = self.request.user.institution
        form.instance.user = self.request.user
        try:
            response = super().form_valid(form)
            messages.success(self.request, _("State definition successfully added."))
            return response
        except IntegrityError:
            messages.error(self.request, _("State is already defined."))
            return self.form_invalid(form)

    def form_invalid(self, form):
        super().form_invalid(form)
        return redirect(self.success_url)


class DeleteStateDefinitionView(AdminView, StateDefinitionContextMixin, SuccessMessageMixin, DeleteView):
    model = StateDefinition
    success_url = reverse_lazy('admin:states_panel')

    def get_success_message(self, cleaned_data):
        return f'State definition: {self.object.state}, has been deleted'

    def form_valid(self, form):
        if not self.object.institution == self.request.user.institution:
            raise Http404

        return super().form_valid(form)


class UpdateStateOrderView(AdminView, TemplateView):
    success_url = reverse_lazy('admin:states_panel')

    def post(self, request, *args, **kwargs):
        form = OrderingStateForm(request.POST)

        if form.is_valid():
            ordered_ids = form.cleaned_data["ordering"].split(',')

            with transaction.atomic():
                current_order = 1
                _log = []
                for lookup_id in ordered_ids:
                    state_definition = StateDefinition.objects.get(id=lookup_id)
                    state_definition.order = current_order
                    state_definition.save()
                    _log.append(f"{state_definition.state} (ID: {lookup_id} -> Order: {current_order})")
                    current_order += 1

            messages.success(self.request, _("Order changed succesfuly."))
            return redirect(self.success_url)
        else:
            return Http404


class UpdateStateDefinitionView(AdminView, UpdateView):
    model = StateDefinition
    template_name = 'states_panel.html'
    fields = ['state']
    success_url = reverse_lazy('admin:states_panel')
    pk_url_kwarg = 'pk'

    def get_queryset(self):
        return StateDefinition.objects.filter(institution=self.request.user.institution)

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
            messages.success(self.request, _("State definition updated successfully."))
            return response
        except IntegrityError:
            messages.error(self.request, _("State is already defined."))
            return self.form_invalid(form)

    def form_invalid(self, form):
        super().form_invalid(form)
        return redirect(self.get_success_url())


class InstitutionLabelCustomizationView(AdminView, UpdateView):
    model = InstitutionLabelSettings
    form_class = InstitutionLabelSettingsForm
    template_name = 'label_settings.html'
    success_url = reverse_lazy('admin:panel')
    breadcrumb = [(_("Admin"), reverse_lazy("admin:panel")), (_("Label Settings"), None)]
    title = _("Edit Label")
    subtitle = _('Manage your label settings')

    def get_object(self, queryset=None):
        institution = self.request.user.institution
        settings, created = InstitutionLabelSettings.objects.get_or_create(institution=institution)
        return settings

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context

    def form_valid(self, form):
        messages.success(self.request, _("QR printing preferences saved successfully."))
        return super().form_valid(form)


class IssueDigitalFacilityRecordView(AdminView, View):
    def post(self, request, *args, **kwargs):
        service = CredentialService(request.user)
        institution = request.user.institution

        geo_data = None
        try:
            raw_lat = request.POST.get('latitude')
            raw_lon = request.POST.get('longitude')

            if raw_lat and raw_lon:
                lat = float(raw_lat)
                lon = float(raw_lon)

                plus_code = olc.encode(lat, lon, 11)
                plus_code_url = f"https://plus.codes/{plus_code}"

                geo_data = {
                    "plusCode": plus_code_url,
                    "geoLocation": {
                        "type": "Point",
                        "coordinates": [lon, lat]
                    }
                }
        except (ValueError, TypeError):
            pass

        address_data = {
            "type": ["Address"],
            "streetAddress": institution.street_address,
            "postalCode": institution.postal_code,
            "addressLocality": institution.location,
            "addressRegion": institution.region,
            "addressCountry": institution.country
        }
        address_data = {k: v for k, v in address_data.items() if v}

        isic_names = {
            '9511': "Repair of computers and peripheral equipment",
            '3830': "Materials recovery and recycling",
            '3313': "Repair of electronic and optical equipment",
            '4649': "Wholesale of other household goods",
            '0000': "General Operations"
        }

        process_code = institution.process_category_code
        process_name = isic_names.get(process_code, "General Operations")
        process_category = [
            {
                "id": f"https://unstats.un.org/unsd/classifications/Econ/ISIC/Rev4/{process_code}",
                "code": process_code,
                "name": process_name,
                "schemeID": "https://unstats.un.org/unsd/classifications/Econ/ISIC/",
                "schemeName": "UN ISIC Rev.4"
            }
        ]

        facility_uri = institution.facility_id_uri or f"urn:uuid:{uuid.uuid4()}"
        facility_data = {
            "type": ["Facility"],
            "id": facility_uri,
            "name": institution.name,
            "description": institution.facility_description,
            "countryOfOperation": institution.country,
            "address": address_data,
            "operatedByParty": {
                "id": facility_uri,
                "name": institution.name,
                "registeredId": institution.registered_id or str(institution.id)
            },
            "locationInformation": geo_data,
            "processCategory": process_category
        }
        if institution.logo:
            facility_data["logo"] = institution.logo
            facility_data["operatedByParty"]["logo"] = institution.logo
        #delete empty fields jic
        facility_data = {k: v for k, v in facility_data.items() if v}

        conformity_claims = []
        for claim in institution.claims.all():
            claim_id = f"urn:uuid:{uuid.uuid4()}"

            claim_data = {
                "id": claim_id,
                "type": ["Claim", "Declaration"],
                "description": claim.description,
                "conformance": True,
                "conformityTopic": claim.topic_code,
            }

            if claim.admin_name:
                claim_data["referenceRegulation"] = {
                    "administeredBy": {
                        "id": claim.admin_url or "urn:uuid:unknown",
                        "name": claim.admin_name
                    }
                }

            if hasattr(claim, 'assessment_date') and claim.assessment_date:
                claim_data["assessmentDate"] = claim.assessment_date.isoformat()

            if hasattr(claim, 'evidence_url') and claim.evidence_url:
                evidence = {
                    "type": ["SecureLink", "Link"],
                    "linkURL": claim.evidence_url
                }
                if hasattr(claim, 'evidence_name') and claim.evidence_name:
                    evidence["linkName"] = claim.evidence_name

                claim_data["conformityEvidence"] = evidence

            conformity_claims.append(claim_data)

        credential_subject = {
            "type": ["FacilityRecord"],
            "id": facility_uri,
            "facility": facility_data
        }
        if conformity_claims:
            credential_subject["conformityClaim"] = conformity_claims

        credential, error = service.issue_facility_credential(
            credential_subject=credential_subject,
            credential_db_key=CredentialProperty.CredentialType.DFR,
            description="Digital Facility Record",
        )
        if error:
            messages.error(request, error)
        else:
            messages.success(request, "Facility Record issued successfully!")

        return redirect('admin:panel')
