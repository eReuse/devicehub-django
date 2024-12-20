import logging
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
from django.core.exceptions import ValidationError
from django.db import IntegrityError,   transaction
from dashboard.mixins import DashboardView, Http403
from admin.forms import OrderingStateForm
from user.models import User, Institution
from admin.email import NotifyActivateUserByEmail
from action.models import StateDefinition


class AdminView(DashboardView):
    def get(self, *args, **kwargs):
        response = super().get(*args, **kwargs)
        if not self.request.user.is_admin:
            raise Http403
        
        return response

class PanelView(AdminView, TemplateView):
    template_name = "admin_panel.html"
    title = _("Admin")
    breadcrumb = _("admin") + " /"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context


class UsersView(AdminView, TemplateView):
    template_name = "admin_users.html"
    title = _("Users")
    breadcrumb = _("admin / Users") + " /"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "users": User.objects.filter()
        })
        return context


class CreateUserView(AdminView, NotifyActivateUserByEmail, CreateView):
    template_name = "user.html"
    title = _("User")
    breadcrumb = _("admin / User") + " /"
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
    breadcrumb = "admin / Delete user"
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
    breadcrumb = "admin / Edit user"
    success_url = reverse_lazy('admin:users')
    model = User
    fields = (
        "email",
        "is_admin",
    )

    def get_form_kwargs(self):
        pk = self.kwargs.get('pk')
        self.object = get_object_or_404(self.model, pk=pk)
        #self.object.set_password(self.object.password)
        kwargs = super().get_form_kwargs()
        return kwargs

    
class InstitutionView(AdminView, UpdateView):
    template_name = "institution.html"
    title = _("Edit institution")
    section = "admin"
    subtitle = _('Edit institution')
    model = Institution
    success_url = reverse_lazy('admin:panel')
    fields = (
        "name",
        "logo",
        "location",
        "responsable_person",
        "supervisor_person"
    )

    def get_form_kwargs(self):
        self.object = self.request.user.institution
        kwargs = super().get_form_kwargs()
        return kwargs


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
    breadcrumb = _("admin / States Panel") + " /"


class AddStateDefinitionView(AdminView, StateDefinitionContextMixin, CreateView):
    template_name = "states_panel.html"
    title = _("New State Definition")
    breadcrumb = "Admin / New state"
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
        return super().form_invalid(form)


class DeleteStateDefinitionView(AdminView, StateDefinitionContextMixin, SuccessMessageMixin, DeleteView):
    model = StateDefinition
    success_url = reverse_lazy('admin:states_panel')

    def get_success_message(self, cleaned_data):
        device_logger.info(f"<Deleted> StateDefinition with value {self.object.state} by user {self.request.user}.")
        return f'State definition: {self.object.state}, has been deleted'

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()

        #only an admin of current institution can delete
        if not object.institution == self.request.user.institution:
            raise Http404

        return super().delete(request, *args, **kwargs)


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

            device_logger.info(
                f"<Updated Order> State order updated by user {self.request.user}: {', '.join(_log)}"
            )
            messages.success(self.request, _("Order changed succesfuly."))
            return redirect(self.success_url)
        else:
            return Http404


class UpdateStateDefinitionView(AdminView, UpdateView):
    model = StateDefinition
    template_name = 'states_panel.html'
    fields = ['state']
    pk_url_kwarg = 'pk'

    def get_queryset(self):
        return StateDefinition.objects.filter(institution=self.request.user.institution)

    def get_success_url(self):
        messages.success(self.request, _("State definition updated successfully."))
        return reverse_lazy('admin:states_panel')

    def form_valid(self, form):
        return super().form_valid(form)
