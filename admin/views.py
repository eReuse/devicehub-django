from smtplib import SMTPException
from django.contrib import messages
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext_lazy as _
from django.views.generic.base import TemplateView
from django.views.generic.edit import (
    CreateView,
    UpdateView,
    DeleteView,
)
from dashboard.mixins import DashboardView, Http403
from user.models import User, Institution
from admin.email import NotifyActivateUserByEmail
from lot.models import LotTag


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


class LotTagPanelView(AdminView, TemplateView):
    template_name = "lot_tag_panel.html"
    title = _("Lot Tag Panel")
    breadcrumb = _("admin / Lot Tag Panel")


class AddLotTagView(AdminView, CreateView):
    template_name = "lot_tag_panel.html"
    title = _("New lot tag Definition")
    breadcrumb = "Admin / New lot tag"
    success_url = reverse_lazy('admin:tag_panel')
    model = LotTag
    fields = ('name',)

    def form_valid(self, form):
        form.instance.owner = self.request.user.institution
        form.instance.user = self.request.user

        response = super().form_valid(form)
        messages.success(self.request, _("Lot Tag successfully added."))
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
            msg = _('This tag have lots. Impossible deleted.')
            messages.warning(self.request, msg)
            return redirect(reverse_lazy('admin:tag_panel'))

        response = super().delete(request, *args, **kwargs)
        msg = _('Lot Tag has been deleted.')
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
        response = super().form_valid(form)
        msg = _("Lot Tag updated successfully.")
        messages.success(self.request, msg)
        return response


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
