import ast
import logging

from django.db import IntegrityError
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, redirect, Http404, render
from django.contrib import messages
from django.core.cache import cache
from django.utils.translation import gettext_lazy as _
from django.db.models import Q, Count, Case, When, IntegerField
from django.views.generic.base import TemplateView, View
from django.views.generic.edit import (
    CreateView,
    DeleteView,
    UpdateView,
    FormView,
)
from django_tables2 import SingleTableView
from dashboard.mixins import DashboardView
from lot.tables import LotTable
from device.models import Device
from evidence.models import SystemProperty
from lot.models import Lot, LotTag, LotProperty
from lot.forms import LotsForm


logger = logging.getLogger(__name__)


class LotSuccessUrlMixin():
    success_url = reverse_lazy('dashboard:unassigned')

    def get_success_url(self, lot_tag=None):
        try:
            if lot_tag:
                lot_group = LotTag.objects.only('id').get(
                    owner=self.request.user.institution,
                    name=lot_tag
                )
            else:
                lot_group = LotTag.objects.only('id').get(
                    owner=self.object.owner,
                    name=self.object.type
                )
            return reverse_lazy('lot:tags', args=[lot_group.id])

        except LotTag.DoesNotExist:
            return self.success_url


class NewLotView(LotSuccessUrlMixin, DashboardView, CreateView):
    template_name = "new_lot.html"
    title = _("New lot")
    breadcrumb = "lot / New lot"
    model = Lot
    fields = (
        "type",
        "name",
        "code",
        "description",
        "archived",
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


class DeleteLotsView(LotSuccessUrlMixin, DashboardView, TemplateView ):
    template_name = "delete_lots.html"
    title = _("Delete lot/s")
    breadcrumb = "lots / Delete"

    def get(self, request, *args, **kwargs):
        selected_ids = request.GET.getlist('select')
        if not selected_ids:
            messages.error(request, _("No lots selected for deletion."))
            return redirect(self.success_url)
        # check ownership
        lots_to_delete = Lot.objects.filter(
            id__in=selected_ids,
            owner=request.user.institution
        )
        context = {
            'lots': lots_to_delete,
            'lots_with_devices': any(lot.devices.exists() for lot in lots_to_delete),
            'selected_ids': selected_ids,
            'breadcrumb': self.breadcrumb,
            'title': self.title,
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        selected_ids = request.POST.getlist('selected_ids')
        if not selected_ids:
            messages.error(request, _("No lots selected for deletion."))
            return redirect(self.success_url)

        lots_to_delete = Lot.objects.filter(
            id__in=selected_ids,
            owner=request.user.institution
        )

        lot_tag = lots_to_delete.first().type
        deleted_count = lots_to_delete.delete()
        messages.success(request, _("Lots succesfully deleted"))
        return redirect(self.get_success_url(lot_tag=lot_tag))


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
        "archived",
    )

    def get_form_kwargs(self):
        pk = self.kwargs.get('pk')
        self.object = get_object_or_404(
            self.model,
            owner=self.request.user.institution,
            pk=pk,
        )
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
        messages.success(self.request, _("Lot edited succesfully."))
        response = super().form_valid(form)
        return response


class AddToLotView(DashboardView, FormView):
    template_name = "list_lots.html"
    title = _("Add to lots")
    breadcrumb = "lot / add to lots"
    success_url = reverse_lazy('dashboard:unassigned')
    form_class = LotsForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lots = Lot.objects.filter(owner=self.request.user.institution).order_by('-created')
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
        messages.success(self.request, _("Devices assigned to Lot."))
        return response

    def get_success_url(self):
        return reverse_lazy('dashboard:lot', args=[self.request.POST.getlist('lots')[0]])


class DelToLotView(DashboardView, View):
    #DashboardView will redirect to a GET method
    def get(self, request, *args, **kwargs):
        lot_id = self.kwargs.get('pk')
        selected_devices = self.get_session_devices()

        if not selected_devices:
            messages.error(request, _("No devices selected"))
            return redirect(reverse_lazy('dashboard:lot', kwargs={'pk': lot_id}))
        try:
            lot = Lot.objects.filter(
                id=lot_id,
            ).first()

            for dev in selected_devices:
                    lot.remove(dev.id)
            msg = _("Successfully unassigned %d devices from the lot")
            messages.success(request, msg % len(selected_devices))

        except Exception as e:
            messages.error(
                request,
                _("Error unassigning devices: %s") % str(e))

        return redirect(reverse_lazy('dashboard:lot', kwargs={'pk': lot_id}))


class LotsTagsView(DashboardView, SingleTableView):
    template_name = "lots.html"
    title = _("Lot group")
    breadcrumb = _("lots") + " /"
    success_url = reverse_lazy('dashboard:unassigned')
    model = Lot
    table_class = LotTable
    paginate_by = 10

    def get_queryset(self):
        self.pk = self.kwargs.get('pk')
        self.tag = get_object_or_404(LotTag, owner=self.request.user.institution, id=self.pk)
        self.show_archived = self.request.GET.get('show_archived', 'false')
        self.search_query = self.request.GET.get('q', '').strip()

        queryset = Lot.objects.filter(owner=self.request.user.institution, type=self.tag).annotate(
            device_count=Count('devicelot')
        )

        if self.show_archived == 'true':
            queryset = queryset.filter(archived=True)
        elif self.show_archived == 'false':
            queryset = queryset.filter(archived=False)

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
        counts = self.get_counts()

        context.update({
            'title': _("Lot Group") + " - " + self.tag.name,
            'breadcrumb': _("Lots") + " / " + self.tag.name,
            'show_archived': self.show_archived,
            'search_query': self.search_query,
            'archived_count': counts['archived_count'],
            'active_count': counts['active_count'],
            'total_count': counts['total_count'],
        })
        return context

    def get_counts(self):
        cache_key = f"lot_counts_{self.request.user.institution.id}_{self.tag.id}"
        counts = cache.get(cache_key)

        if not counts:
            # calculate archived, open, and total count on a single query
            counts = Lot.objects.filter(owner=self.request.user.institution, type=self.tag).aggregate(
                archived_count=Count(Case(When(archived=True, then=1), output_field=IntegerField())),
                active_count=Count(Case(When(archived=False, then=1), output_field=IntegerField())),
                total_count=Count('id')
            )
            cache.set(cache_key, counts, timeout=250)

        return counts


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
