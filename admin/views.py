import logging
from smtplib import SMTPException

from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db import IntegrityError, transaction
from django.shortcuts import Http404, get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.functional import cached_property
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
from device.models import DeviceType, DeviceTypeAttribute
from django_tables2 import SingleTableView
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

    def get_form_kwargs(self):
        self.object = self.request.user.institution
        kwargs = super().get_form_kwargs()
        return kwargs

    def form_valid(self, form):
        logger.info(f"User {self.request.user.id} updated organization profile.")
        messages.success(self.request, _("Organization profile updated successfully."))
        return super().form_valid(form)


class StateDefinitionContextMixin(ContextMixin):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "state_definitions": StateDefinition.objects.filter(institution=self.request.user.institution).order_by('order'),
            "help_text": _('State definitions are the custom finite states that a product can be in.'),
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


class DeviceTypeContextMixin(ContextMixin):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "device_types": DeviceType.objects.filter(
                institution=self.request.user.institution
            ).order_by('order'),
        })
        return context


class DeviceTypesPanelView(AdminView, DeviceTypeContextMixin, TemplateView):
    template_name = "device_types_panel.html"
    title = _("Product Types Panel")
    breadcrumb = [(_("Admin"), reverse_lazy("admin:panel")), (_("Product Types"), None)]


class AddDeviceTypeView(AdminView, DeviceTypeContextMixin, CreateView):
    template_name = "device_types_panel.html"
    title = _("New Product Type")
    breadcrumb = [
        (_("Admin"), reverse_lazy("admin:panel")),
        (_("Product Types"), reverse_lazy("admin:devicetypes_panel")),
        (_("New product type"), None),
    ]
    success_url = reverse_lazy('admin:devicetypes_panel')
    model = DeviceType
    fields = ('name', 'label', 'icon')

    def form_valid(self, form):
        form.instance.institution = self.request.user.institution
        try:
            with transaction.atomic():
                response = super().form_valid(form)
            messages.success(self.request, _("Product type successfully added."))
            return response
        except IntegrityError:
            messages.error(self.request, _("Product type is already defined."))
            return redirect(self.success_url)

    def form_invalid(self, form):
        return redirect(self.success_url)


class DeleteDeviceTypeView(AdminView, DeviceTypeContextMixin, SuccessMessageMixin, DeleteView):
    model = DeviceType
    success_url = reverse_lazy('admin:devicetypes_panel')

    def get_success_message(self, cleaned_data):
        return f'Product type: {self.object.name}, has been deleted'

    def form_valid(self, form):
        if not self.object.institution == self.request.user.institution:
            raise Http404
        return super().form_valid(form)


class UpdateDeviceTypeOrderView(AdminView, TemplateView):
    success_url = reverse_lazy('admin:devicetypes_panel')

    def post(self, request, *args, **kwargs):
        form = OrderingStateForm(request.POST)

        if form.is_valid():
            ordered_ids = form.cleaned_data["ordering"].split(',')

            with transaction.atomic():
                current_order = 1
                for lookup_id in ordered_ids:
                    device_type = DeviceType.objects.get(id=lookup_id)
                    device_type.order = current_order
                    device_type.save()
                    current_order += 1

            messages.success(self.request, _("Order changed successfully."))
            return redirect(self.success_url)
        else:
            return Http404


class UpdateDeviceTypeView(AdminView, UpdateView):
    model = DeviceType
    template_name = 'device_types_panel.html'
    fields = ['name', 'label', 'icon']
    success_url = reverse_lazy('admin:devicetypes_panel')
    pk_url_kwarg = 'pk'

    def get_queryset(self):
        return DeviceType.objects.filter(institution=self.request.user.institution)

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
            messages.success(self.request, _("Product type updated successfully."))
            return response
        except IntegrityError:
            messages.error(self.request, _("Product type is already defined."))
            return self.form_invalid(form)

    def form_invalid(self, form):
        super().form_invalid(form)
        return redirect(self.get_success_url())


class AdminWriteView(AdminView):
    # AdminView only checks is_admin on GET, so a view that answers POST would
    # let any authenticated user through. Anonymous users fall through to
    # LoginRequiredMixin, which runs later in the MRO.
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.is_admin:
            raise Http403
        return super().dispatch(request, *args, **kwargs)


class DeviceTypeAttributeContextMixin(ContextMixin):
    """For the views that hang off a single product type, taken from the URL."""

    @cached_property
    def device_type(self):
        return get_object_or_404(
            DeviceType,
            pk=self.kwargs['type_pk'],
            institution=self.request.user.institution,
        )

    def get_success_url(self):
        return reverse('admin:attributes_panel', args=[self.device_type.pk])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "device_type": self.device_type,
            "attributes": self.device_type.attributes.all(),
            "breadcrumb": [
                (_("Admin"), reverse('admin:panel')),
                (_("Product Types"), reverse('admin:devicetypes_panel')),
                (self.device_type.display_name, None),
            ],
        })
        return context


class DeviceTypeAttributesPanelView(
    AdminWriteView, DeviceTypeAttributeContextMixin, TemplateView
):
    template_name = "device_type_attributes_panel.html"
    title = _("Product Type Attributes")


class AddDeviceTypeAttributeView(
    AdminWriteView, DeviceTypeAttributeContextMixin, CreateView
):
    template_name = "device_type_attributes_panel.html"
    title = _("New Attribute")
    model = DeviceTypeAttribute
    fields = ('name',)

    def form_valid(self, form):
        form.instance.device_type = self.device_type
        try:
            with transaction.atomic():
                response = super().form_valid(form)
            messages.success(self.request, _("Attribute successfully added."))
            return response
        except IntegrityError:
            messages.error(self.request, _("Attribute is already defined."))
            return redirect(self.get_success_url())

    def form_invalid(self, form):
        return redirect(self.get_success_url())


class DeviceTypeAttributeScopedMixin:
    """For the views addressing an attribute by its own pk."""

    model = DeviceTypeAttribute

    def get_queryset(self):
        return DeviceTypeAttribute.objects.filter(
            device_type__institution=self.request.user.institution
        )

    def get_success_url(self):
        return reverse('admin:attributes_panel', args=[self.object.device_type_id])


class UpdateDeviceTypeAttributeView(
    AdminWriteView, DeviceTypeAttributeScopedMixin, UpdateView
):
    template_name = 'device_type_attributes_panel.html'
    fields = ['name']
    pk_url_kwarg = 'pk'

    def form_valid(self, form):
        try:
            with transaction.atomic():
                response = super().form_valid(form)
            messages.success(self.request, _("Attribute updated successfully."))
            return response
        except IntegrityError:
            messages.error(self.request, _("Attribute is already defined."))
            return redirect(self.get_success_url())

    def form_invalid(self, form):
        return redirect(self.get_success_url())


class DeleteDeviceTypeAttributeView(
    AdminWriteView, DeviceTypeAttributeScopedMixin, SuccessMessageMixin, DeleteView
):

    def get_success_message(self, cleaned_data):
        return _("Attribute {} has been deleted").format(self.object.name)


class UpdateDeviceTypeAttributeOrderView(
    AdminWriteView, DeviceTypeAttributeContextMixin, TemplateView
):

    def post(self, request, *args, **kwargs):
        form = OrderingStateForm(request.POST)
        if not form.is_valid():
            raise Http404

        ordered_ids = form.cleaned_data["ordering"].split(',')
        attributes = {
            str(attribute.pk): attribute
            for attribute in self.device_type.attributes.all()
        }
        if set(ordered_ids) != set(attributes):
            raise Http404

        with transaction.atomic():
            for order, lookup_id in enumerate(ordered_ids, start=1):
                attribute = attributes[lookup_id]
                attribute.order = order
                attribute.save()

        messages.success(self.request, _("Order changed successfully."))
        return redirect(self.get_success_url())


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


class DPPConfigurationView(AdminView, UpdateView):
    template_name = "dpp_settings.html"
    model = InstitutionDPPSettings
    form_class = InstitutionDPPSettingsForm
    breadcrumb = [(_("Admin"), reverse_lazy("admin:panel")), (_("Digital Product Passport"), None)]
    title = _("Integration & Digital Product Passports")
    subtitle = _("Manage schemas, conformity claims, and automated traceability")

    def get_success_url(self):
        return reverse_lazy('admin:dpp_settings', kwargs={'pk': self.request.user.institution.pk})

    def get_object(self, queryset=None):
        obj, created = InstitutionDPPSettings.objects.get_or_create(
            institution=self.request.user.institution
        )
        return obj

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        service = CredentialService(self.request.user)
        self.schemas = service.fetch_schemas()
        kwargs['schemas'] = self.schemas
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        institution = self.request.user.institution

        context['subtitle'] = _("Digital Product Passport Configuration")
        context['states'] = StateDefinition.objects.filter(institution=institution).order_by('order')

        # locks for buttons
        context['is_institution_complete'] = bool(institution.name and institution.country and institution.street_address)
        context['api_connected'] = bool(getattr(self, 'schemas', False))

        if 'claim_formset' not in kwargs:
            context['claim_formset'] = FacilityClaimFormSet(
                instance=institution,
                prefix='claims'
            )

        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        institution = self.request.user.institution
        action = request.POST.get('action')

        #check which form ahs been submitted
        if action == 'save_dpp':
            form = self.get_form()
            if form.is_valid():
                form.save()
                messages.success(request, _("IdHub integration settings saved successfully."))

                return redirect(f"{self.get_success_url()}#connection")
            else:
                messages.error(request, _("Please correct the errors in the integration settings."))
                return self.render_to_response(self.get_context_data(form=form))

        elif action == 'save_claims':
            claim_formset = FacilityClaimFormSet(request.POST, instance=institution, prefix='claims')
            if claim_formset.is_valid():
                claim_formset.save()
                messages.success(request, _("Facility Conformity Claims updated successfully."))
                return redirect(f"{self.get_success_url()}#claims")
            else:
                messages.error(request, _("Please correct the errors in the conformity claims."))
                return self.render_to_response(self.get_context_data(claim_formset=claim_formset))

        elif action == 'save_states':
            state_ids = request.POST.getlist('state_ids')
            with transaction.atomic():
                for sid in state_ids:
                    is_checked = request.POST.get(f'state_dte_{sid}') == 'on'
                    state_obj = StateDefinition.objects.filter(id=sid, institution=institution).first()

                    if not state_obj:
                        continue

                    dte_config = {}
                    prefix = 'dte_cfg_'
                    suffix = f'_{sid}'

                    has_config_data = False
                    for key, value in request.POST.items():
                        if key.startswith(prefix) and key.endswith(suffix):
                            has_config_data = True
                            clean_key = key[len(prefix):-len(suffix)]
                            if value.strip():
                                dte_config[clean_key] = value.strip()

                    if has_config_data:
                        state_obj.dte_config = dte_config

                    state_obj.auto_issue_dte = is_checked
                    state_obj.save()

            messages.success(request, _("Traceability automation rules saved successfully."))
            return redirect(f"{self.get_success_url()}#states")
        return super().post(request, *args, **kwargs)
