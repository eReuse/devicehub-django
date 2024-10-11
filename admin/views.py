from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.views.generic.base import TemplateView
from django.views.generic.edit import (
    CreateView,
    UpdateView,
    DeleteView,
)
from dashboard.mixins import DashboardView
from user.models import User, Institution


class PanelView(DashboardView, TemplateView):
    template_name = "admin_panel.html"
    title = _("Admin")
    breadcrumb = _("admin") + " /"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context


class UsersView(DashboardView, TemplateView):
    template_name = "admin_users.html"
    title = _("Users")
    breadcrumb = _("admin / Users") + " /"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "users": User.objects.filter()
        })
        return context


class CreateUserView(DashboardView, CreateView):
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
        return response


class DeleteUserView(DashboardView, DeleteView):
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


class EditUserView(DashboardView, UpdateView):
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

    
class InstitutionView(DashboardView, UpdateView):
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
