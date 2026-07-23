import logging
from smtplib import SMTPException

from django_tables2 import SingleTableView
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db import IntegrityError, transaction
from django.shortcuts import Http404, get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic.base import ContextMixin, TemplateView
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from action.models import StateDefinition
from admin.email import NotifyActivateUserByEmail
from admin.forms import (
    FacilityClaimFormSet,
    InstitutionDPPSettingsForm,
    InstitutionForm,
    InstitutionLabelSettingsForm,
    OrderingStateForm,
)
from admin.tables import UserTable
from credentials.services import CredentialService
from dashboard.mixins import DashboardView, Http403
from lot.models import LotTag
from user.models import (
    Institution,
    InstitutionDPPSettings,
    InstitutionLabelSettings,
    User,
)

logger = logging.getLogger('django')

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
        if 'claim_formset' not in kwargs:
            context['claim_formset'] = FacilityClaimFormSet(
                instance=self.object,
                prefix='claims'
            )
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form_class = self.get_form_class()
        form = self.get_form(form_class)

        claim_formset = FacilityClaimFormSet(
            self.request.POST,
            instance=self.object,
            prefix='claims'
        )

        if form.is_valid() and claim_formset.is_valid():
            return self.form_valid(form, claim_formset)
        else:
            return self.form_invalid(form, claim_formset)

    def form_valid(self, form, claim_formset):
        logger.info(f"User {self.request.user.id} updating institution {self.object.id} and its claims.")

        try:
            with transaction.atomic():
                self.object = form.save()
                claim_formset.instance = self.object
                claim_formset.save()

            messages.success(self.request, _("Institution information and claims updated successfully."))
            return super().form_valid(form)

        except Exception as e:
            logger.exception(f"Database error saving institution {self.object.id}: {str(e)}")
            messages.error(self.request, _("An unexpected database error occurred. Please try again."))
            return self.render_to_response(self.get_context_data(form=form, claim_formset=claim_formset))

    def form_invalid(self, form, claim_formset):
        logger.warning(f"User {self.request.user.id} submitted invalid institution form data.")
        messages.error(self.request, _("Please correct the errors below."))
        return self.render_to_response(self.get_context_data(form=form, claim_formset=claim_formset))


class InstitutionConfigView(AdminView, UpdateView):
    template_name = "dpp_settings.html"
    Model = InstitutionDPPSettings
    form_class = InstitutionDPPSettingsForm
    title = _("Configuration & Signing")
    subtitle = _("Manage technical settings and signing credentials")
    success_url = reverse_lazy('admin:panel')

    def get_object(self, queryset=None):
        institution = self.request.user.institution
        obj, created = InstitutionDPPSettings.objects.get_or_create(institution=institution)
        return obj

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        service = CredentialService(self.request.user)
        kwargs['schemas'] = service.fetch_schemas()

        return kwargs

    def form_valid(self, form):
        logger.info(f"User {self.request.user.id} updated DPP integration settings for institution {self.object.institution_id}.")
        messages.success(self.request, _("Configuration updated successfully."))
        return super().form_valid(form)


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
            logger.info(f"User {self.request.user.id} created new state definition: '{form.instance.state}'.")
            messages.success(self.request, _("State definition successfully added."))
            return response
        except IntegrityError:
            logger.warning(f"User {self.request.user.id} attempted to create duplicate state definition '{form.instance.state}'.")
            messages.error(self.request, _("State is already defined."))
            return self.form_invalid(form)

    def form_invalid(self, form):
        super().form_invalid(form)
        return redirect(self.success_url)


class DeleteStateDefinitionView(AdminView, StateDefinitionContextMixin, SuccessMessageMixin, DeleteView):
    model = StateDefinition
    success_url = reverse_lazy('admin:states_panel')

    def get_success_message(self, cleaned_data):
        return _("State definition: {state}, has been deleted").format(state=self.object.state)

    def form_valid(self, form):
        if not self.object.institution == self.request.user.institution:
            logger.warning(f"User {self.request.user.id} attempted to delete state definition belonging to another institution.")
            raise Http404

        state_name = self.object.state
        response = super().form_valid(form)
        logger.info(f"User {self.request.user.id} deleted state definition: '{state_name}'.")
        return response


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
            logger.info(f"User {self.request.user.id} updated state definition to '{form.instance.state}'.")
            messages.success(self.request, _("State definition updated successfully."))
            return response
        except IntegrityError:
            logger.warning(f"User {self.request.user.id} attempted to rename state definition to existing name '{form.instance.state}'.")
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
        logger.info(f"User {self.request.user.id} updated label print settings for institution {self.request.user.institution_id}.")
        messages.success(self.request, _("QR printing preferences saved successfully."))
        return super().form_valid(form)


class IssueDigitalFacilityRecordView(AdminView, View):

    def post(self, request, *args, **kwargs):
        logger.info(f"User {request.user.id} requested Digital Facility Record issuance.")
        service = CredentialService(request.user)

        credential, error = service.issue_credential(
            workflow_type='facility',
            build_kwargs={
                'institution': request.user.institution,
                'request_data': request.POST,
            },
            description="Digital Facility Record"
        )

        if error:
            logger.error(f"Facility Record issuance failed for institution {request.user.institution_id}: {error}")
            messages.error(request, _("Failed to issue Facility Record: {error}").format(error=error))
        else:
            logger.info(f"Successfully issued Facility Record for institution {request.user.institution_id}.")
            messages.success(request, _("Facility Record issued successfully!"))

        return redirect('admin:panel')
