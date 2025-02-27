from django.db import IntegrityError
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, redirect, Http404
from django.contrib import messages
from dashboard.mixins import InventaryMixin, DetailsMixin
from django.utils.translation import gettext_lazy as _
from django.utils.safestring import mark_safe
from django.views.generic.base import TemplateView
from django.db.models import Q
from django.views.generic.edit import (
    CreateView,
    DeleteView,
    UpdateView,
    FormView,
)
import django_tables2 as tables
from dashboard.mixins import DashboardView
from evidence.models import SystemProperty
from device.models import Device
from lot.models import Lot, LotTag, LotProperty
from lot.forms import LotsForm


class LotSuccessUrlMixin():
    success_url = reverse_lazy('lot:unassigned') #default_url

    def get_success_url(self):
        lot_group_id = LotTag.objects.only('id').get(
            owner=self.object.owner,
            name=self.object.type
        ).id

        #null checking just in case
        if not lot_group_id:
            return self.success_url

        return reverse_lazy('lot:tags', args=[lot_group_id])


class NewLotView(LotSuccessUrlMixin ,DashboardView, CreateView):
    template_name = "new_lot.html"
    title = _("New lot")
    breadcrumb = "lot / New lot"
    model = Lot
    fields = (
        "type",
        "name",
        "code",
        "description",
        "closed",
    )

    def get_form(self):
        form = super().get_form()
        form.fields["type"].queryset = LotTag.objects.filter(
            owner=self.request.user.institution,
            inbox=False
        )
        return form

    def form_valid(self, form):
        try:
            form.instance.owner = self.request.user.institution
            form.instance.user = self.request.user
            response = super().form_valid(form)

            messages.success(self.request, _("Lot created successfully."))
            return response

        except IntegrityError:
            messages.error(self.request, _("Lot name is already defined."))
            return self.form_invalid(form)

        return response

class DeleteLotView(LotSuccessUrlMixin, DashboardView, DeleteView):
    template_name = "delete_lot.html"
    title = _("Delete lot")
    breadcrumb = "lot / Delete lot"
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
        messages.warning(self.request, _("Lot '{}' was successfully deleted.").format(self.object.name))
        return response

    def form_invalid(self, form):
        response = super().form_invalid(form)
        messages.error(self.request, _("Error deleting the lot."))
        return response


class EditLotView(LotSuccessUrlMixin, DashboardView, UpdateView):
    template_name = "new_lot.html"
    title = _("Edit lot")
    breadcrumb = "Lot / Edit lot"

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

    def get_form(self):
        form = super().get_form()
        form.fields["type"].queryset = LotTag.objects.filter(
            owner=self.request.user.institution,
            inbox=False
        )
        return form

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.warning(self.request, _("Lot '{}' was successfully edited.").format(self.object.name))
        return response

    def form_invalid(self, form):
        response = super().form_invalid(form)
        messages.error(self.request, _("Error editing the lot."))
        return response


class AddToLotView(DashboardView, FormView):
    template_name = "list_lots.html"
    title = _("Add to lots")
    breadcrumb = "lot / add to lots"
    success_url = reverse_lazy('lot:unassigned')
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


class LotTable(tables.Table):
    name = tables.Column(linkify=("lot:lot", {"pk": tables.A("id")}), verbose_name=_("Lot Name"), attrs={"td": {"class": "fw-bold"}})
    description = tables.Column(verbose_name=_("Description"), default=_("No description"),attrs={"td": {"class": "text-muted"}} )
    closed = tables.Column(verbose_name=_("Status"))
    created = tables.DateColumn(format="Y-m-d", verbose_name=_("Created On"))
    user = tables.Column(verbose_name=("Created By"), default=_("Unknown"), attrs={"td": {"class": "text-muted"}} )
    actions = tables.TemplateColumn(
        template_name="lot_actions.html",
        verbose_name=_(""),
        attrs={"td": {"class": "text-end"}}
    )

    def render_closed(self, value):
        if value:
            return mark_safe('<span class="badge bg-danger">Closed</span>')
        return mark_safe('<span class="badge bg-success">Open</span>')

    class Meta:
        model = Lot
        fields = ("closed", "name", "description", "created", "user", "actions")
        attrs = {
            "class": "table table-hover align-middle",
            "thead": {"class": "table-light"}
        }
        order_by = ("-created",)


class LotsTagsView(DashboardView, tables.SingleTableView):
    template_name = "lots.html"
    title = _("Lot group")
    breadcrumb = _("lots") + " /"
    success_url = reverse_lazy('lot:unassigned')
    model = Lot
    table_class = LotTable

    def get_queryset(self):
        self.pk = self.kwargs.get('pk')
        self.tag = get_object_or_404(LotTag, owner=self.request.user.institution, id=self.pk)
        self.show_open = self.request.GET.get('show_open', 'false') == 'true'
        self.show_closed = self.request.GET.get('show_closed', 'false')
        self.search_query = self.request.GET.get('q', '').strip()

        queryset = Lot.objects.filter(owner=self.request.user.institution, type=self.tag)

        if self.show_closed == 'true':
            queryset = queryset.filter(closed=True)
        elif self.show_closed == 'false':
            queryset = queryset.filter(closed=False)

        if self.search_query:
            queryset = queryset.filter(
                Q(name__icontains=self.search_query) |
                Q(description__icontains=self.search_query) |
                Q(code__icontains=self.search_query)
            )

        sort = self.request.GET.get('sort')
        if sort:
            queryset = queryset.order_by(sort)

        return queryset


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'title': self.title + " " + self.tag.name,
            'breadcrumb': self.breadcrumb + " " + self.tag.name,
            'show_closed': self.show_closed,
            'search_query': self.search_query,
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
    success_url = reverse_lazy('lot:unassigned_devices')
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


class UnassignedDevicesView(InventaryMixin):
    template_name = "unassigned_devices.html"
    section = "Unassigned"
    title = _("Unassigned Devices")
    breadcrumb = "Devices / Unassigned Devices"

    def get_devices(self, user, offset, limit):
        return Device.get_unassigned(self.request.user.institution, offset, limit)

class LotView(InventaryMixin, DetailsMixin):
    template_name = "unassigned_devices.html"
    section = "dashboard_lot"
    breadcrumb = "Lot / Devices"
    model = Lot

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lot = context.get('object')
        context.update({
            'lot': lot,
            'title': _("Lot {}".format(lot.name))
        })
        return context

    def get_devices(self, user, offset, limit):
        chids = self.object.devicelot_set.all().values_list(
            "device_id", flat=True
        ).distinct()

        props = SystemProperty.objects.filter(
            owner=self.request.user.institution,
            value__in=chids
        ).order_by("-created")

        chids_ordered = []
        for x in props:
            if x.value not in chids_ordered:
                chids_ordered.append(x.value)

        chids_page = chids_ordered[offset:offset+limit]
        return [Device(id=x) for x in chids_page], len(chids_ordered)
