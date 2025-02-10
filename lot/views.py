from django.db import IntegrityError
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, redirect, Http404
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.views.generic.base import TemplateView
from django.views.generic.edit import (
    CreateView,
    DeleteView,
    UpdateView,
    FormView,
)
from dashboard.mixins import DashboardView
from lot.models import Lot, LotTag, LotProperty
from lot.forms import LotsForm

class NewLotView(DashboardView, CreateView):
    template_name = "new_lot.html"
    title = _("New lot")
    breadcrumb = "lot / New lot"
    success_url = reverse_lazy('dashboard:unassigned_devices')
    model = Lot
    fields = (
        "type",
        "name",
        "code",
        "description",
        "closed",
    )

    def form_valid(self, form):
        form.instance.owner = self.request.user.institution
        form.instance.user = self.request.user
        response = super().form_valid(form)
        return response


class DeleteLotView(DashboardView, DeleteView):
    template_name = "delete_lot.html"
    title = _("Delete lot")
    breadcrumb = "lot / Delete lot"
    success_url = reverse_lazy('dashboard:unassigned_devices')
    model = Lot
    fields = (
        "type",
        "name",
        "code",
        "description",
        "closed",
    )

    def form_valid(self, form):
        response = super().form_valid(form)
        return response


class EditLotView(DashboardView, UpdateView):
    template_name = "new_lot.html"
    title = _("Edit lot")
    breadcrumb = "Lot / Edit lot"
    success_url = reverse_lazy('dashboard:unassigned_devices')
    model = Lot
    fields = (
        "type",
        "name",
        "code",
        "description",
        "closed",
    )

    def get_form_kwargs(self):
        pk = self.kwargs.get('pk')
        self.object = get_object_or_404(
            self.model,
            owner=self.request.user.institution,
            pk=pk,
        )
        # self.success_url = reverse_lazy('dashbiard:lot', args=[pk])
        kwargs = super().get_form_kwargs()
        return kwargs


class AddToLotView(DashboardView, FormView):
    template_name = "list_lots.html"
    title = _("Add to lots")
    breadcrumb = "lot / add to lots"
    success_url = reverse_lazy('dashboard:unassigned_devices')
    form_class = LotsForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lots = Lot.objects.filter(owner=self.request.user.institution)
        lot_tags = LotTag.objects.filter(owner=self.request.user.institution)
        context.update({
            'lots': lots,
            'lot_tags':lot_tags,
        })
        return context

    def get_form(self):
        form = super().get_form()
        form.fields["lots"].queryset = Lot.objects.filter(
            owner=self.request.user.institution)
        return form

    def form_valid(self, form):
        form.devices = self.get_session_devices()
        form.save()
        response = super().form_valid(form)
        return response


class DelToLotView(AddToLotView):
    title = _("Remove from lots")
    breadcrumb = "lot / remove from lots"

    def form_valid(self, form):
        form.devices = self.get_session_devices()
        form.remove()
        response = super().form_valid(form)
        return response


class LotsTagsView(DashboardView, TemplateView):
    template_name = "lots.html"
    title = _("lots")
    breadcrumb = _("lots") + " /"
    success_url = reverse_lazy('dashboard:unassigned_devices')

    def get_context_data(self, **kwargs):
        self.pk = kwargs.get('pk')
        context = super().get_context_data(**kwargs)
        tag = get_object_or_404(LotTag, owner=self.request.user.institution, id=self.pk)
        self.title += " {}".format(tag.name)
        self.breadcrumb += " {}".format(tag.name)
        show_closed = self.request.GET.get('show_closed', 'false') == 'true'
        lots = Lot.objects.filter(owner=self.request.user.institution).filter(
            type=tag, closed=show_closed
        )
        context.update({
            'lots': lots,
            'title': self.title,
            'breadcrumb': self.breadcrumb,
            'show_closed': show_closed
        })
        return context


class LotPropertiesView(DashboardView, TemplateView):
    template_name = "properties.html"
    title = _("New Lot Property")
    breadcrumb = "Lot / New property"

    def get_context_data(self, **kwargs):
        self.pk = kwargs.get('pk')
        context = super().get_context_data(**kwargs)
        lot = get_object_or_404(Lot, owner=self.request.user.institution, id=self.pk)
        properties = LotProperty.objects.filter(
            lot=lot,
            owner=self.request.user.institution,
            type=LotProperty.Type.USER,
        )
        context.update({
            'lot': lot,
            'properties': properties,
            'title': self.title,
            'breadcrumb': self.breadcrumb
        })
        return context


class AddLotPropertyView(DashboardView, CreateView):
    template_name = "new_property.html"
    title = _("New Lot Property")
    breadcrumb = "Device / New property"
    success_url = reverse_lazy('dashboard:unassigned_devices')
    model = LotProperty
    fields = ("key", "value")

    def form_valid(self, form):
        form.instance.owner = self.request.user.institution
        form.instance.user = self.request.user
        form.instance.lot = self.lot
        form.instance.type = LotProperty.Type.USER
        try:
            response = super().form_valid(form)
            messages.success(self.request, _("Property successfully added."))
            return response
        except IntegrityError:
            messages.error(self.request, _("Property is already defined."))
            return self.form_invalid(form)

    def get_form_kwargs(self):
        pk = self.kwargs.get('pk')
        self.lot = get_object_or_404(Lot, pk=pk, owner=self.request.user.institution)
        self.success_url = reverse_lazy('lot:properties', args=[pk])
        kwargs = super().get_form_kwargs()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['lot_id'] = self.lot.id
        return context


class UpdateLotPropertyView(DashboardView, UpdateView):
    template_name = "properties.html"
    title = _("Update lot Property")
    breadcrumb = "Lot / Update Property"
    model = LotProperty
    fields = ("key", "value")

    def get_form_kwargs(self):
        pk = self.kwargs.get('pk')
        lot_property = get_object_or_404(
            LotProperty,
            pk=pk,
            owner=self.request.user.institution
        )

        if not lot_property:
            raise Http404

        lot_pk = lot_property.lot.pk
        self.success_url = reverse_lazy('lot:properties', args=[lot_pk])
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = lot_property
        return kwargs

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
            messages.success(self.request, _("Property updated successfully."))
            return response
        except IntegrityError:
            messages.error(self.request, _("Property is already defined."))
            return self.form_invalid(form)

    def form_invalid(self, form):
        super().form_invalid(form)
        return redirect(self.get_success_url())


class DeleteLotPropertyView(DashboardView, DeleteView):
    model = LotProperty

    def post(self, request, *args, **kwargs):
        self.pk = kwargs['pk']
        self.object = get_object_or_404(
            self.model,
            pk=self.pk,
            owner=self.request.user.institution
        )
        lot_pk = self.object.lot.pk
        self.object.delete()
        messages.success(self.request, _("Lot property deleted successfully."))
        self.success_url = reverse_lazy('lot:properties', args=[lot_pk])

        # Redirect back to the original URL
        return redirect(self.success_url)
