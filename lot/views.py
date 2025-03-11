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
from evidence.models import SystemProperty
from device.models import Device
from lot.models import Lot, LotTag, LotProperty, LotSubscription, Donor
from lot.forms import LotsForm, LotSubscriptionForm, AddDonorForm

class NewLotView(DashboardView, CreateView):
    template_name = "new_lot.html"
    title = _("New lot")
    breadcrumb = "lot / New lot"
    success_url = reverse_lazy('dashboard:unassigned')
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
        form.instance.owner = self.request.user.institution
        form.instance.user = self.request.user
        response = super().form_valid(form)
        return response


class DeleteLotView(DashboardView, DeleteView):
    template_name = "delete_lot.html"
    title = _("Delete lot")
    breadcrumb = "lot / Delete lot"
    success_url = reverse_lazy('dashboard:unassigned')
    model = Lot
    fields = (
        "type",
        "name",
        "code",
        "description",
        "archived",
    )

    def form_valid(self, form):
        response = super().form_valid(form)
        return response


class EditLotView(DashboardView, UpdateView):
    template_name = "new_lot.html"
    title = _("Edit lot")
    breadcrumb = "Lot / Edit lot"
    success_url = reverse_lazy('dashboard:unassigned')
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
        # self.success_url = reverse_lazy('dashboard:lot', args=[pk])
        kwargs = super().get_form_kwargs()
        return kwargs

    def get_form(self):
        form = super().get_form()
        form.fields["type"].queryset = LotTag.objects.filter(
            owner=self.request.user.institution,
            inbox=False
        )
        return form


class AddToLotView(DashboardView, FormView):
    template_name = "list_lots.html"
    title = _("Add to lots")
    breadcrumb = "lot / add to lots"
    success_url = reverse_lazy('dashboard:unassigned')
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
    success_url = reverse_lazy('dashboard:unassigned')

    def get_context_data(self, **kwargs):
        self.pk = kwargs.get('pk')
        context = super().get_context_data(**kwargs)
        tag = get_object_or_404(LotTag, owner=self.request.user.institution, id=self.pk)
        self.title += " {}".format(tag.name)
        self.breadcrumb += " {}".format(tag.name)
        show_archived = self.request.GET.get('show_archived', 'false') == 'true'
        lots = Lot.objects.filter(owner=self.request.user.institution).filter(
            type=tag, archived=show_archived
        )
        context.update({
            'lots': lots,
            'title': self.title,
            'breadcrumb': self.breadcrumb,
            'show_archived': show_archived
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


class SubscriptLotMixing(DashboardView, FormView):
    template_name = "subscription.html"
    title = _("Subscription")
    breadcrumb = "Lot / Subscription"
    form_class = LotSubscriptionForm
    lot = None


    def get_context_data(self, **kwargs):
        self.pk = self.kwargs.get('pk')
        context = super().get_context_data(**kwargs)
        self.get_lot()
        context.update({
            'lot': self.lot,
            "action": _("Subscribe")
        })
        return context

    def get_form_kwargs(self):
        self.pk = self.kwargs.get('pk')
        self.success_url = reverse_lazy('dashboard:lot', args=[self.pk])
        kwargs = super().get_form_kwargs()
        kwargs["institution"] = self.request.user.institution
        kwargs["lot_pk"] = self.pk
        return kwargs

    def get_lot(self):
        self.lot = get_object_or_404(
            Lot,
            owner=self.request.user.institution,
            id=self.pk
        )


class SubscriptLotView(SubscriptLotMixing):

    def form_valid(self, form):
        form.save()
        response = super().form_valid(form)
        return response


class UnsubscriptLotView(SubscriptLotMixing):
    title = _("Unsubscription")
    breadcrumb = "Lot / Unsubscription"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["action"] = _("Unsubscribe")
        return context

    def form_valid(self, form):
        form.remove()
        response = super().form_valid(form)
        return response


class DonorMixing(DashboardView, FormView):
    template_name = "donor.html"
    form_class = AddDonorForm
    lot = None
    donor = None

    def get_context_data(self, **kwargs):
        self.pk = self.kwargs.get('pk')
        context = super().get_context_data(**kwargs)
        if not self.lot:
            self.get_lot()
        if not self.donor:
            self.get_donor()

        context.update({
            'lot': self.lot,
            'donor': self.donor,
        })
        return context

    def get_form_kwargs(self):

        self.pk = self.kwargs.get('pk')
        self.success_url = reverse_lazy('dashboard:lot', args=[self.pk])
        self.get_lot()
        self.get_donor()
        cmanager = LotSubscription.objects.filter(
            lot=self.lot,
            is_circuit_manager=True,
            user=self.request.user
        ).first()

        if not self.request.user.is_admin and not cmanager:
            raise Http404

        kwargs = super().get_form_kwargs()
        kwargs["institution"] = self.request.user.institution
        kwargs["lot"] = self.lot
        if self.donor:
            kwargs["initial"] = {"user": self.donor.email}
            kwargs["donor"] = self.donor
        return kwargs

    def get_lot(self):
        self.lot = get_object_or_404(
            Lot,
            owner=self.request.user.institution,
            id=self.pk
        )

    def get_donor(self):
        if not self.lot:
            self.get_lot()

        self.donor = Donor.objects.filter(
            lot=self.lot,
        ).first()

class AddDonorView(DonorMixing):
    title = _("Add Donor")
    breadcrumb = "Lot / {}".format(title)

    def form_valid(self, form):
        form.save()
        response = super().form_valid(form)
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["action"] = _("Add")
        return context


class DelDonorView(DonorMixing):
    title = _("Remove Donor")
    breadcrumb = "Lot / {}".format(title)

    def form_valid(self, form):
        form.remove()
        response = super().form_valid(form)
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["action"] = _("Remove")
        return context


class DonorView(TemplateView):
    template_name = "donor_web.html"

    def get_context_data(self, **kwargs):
        pk = self.kwargs.get('pk')
        id = self.kwargs.get('id')

        self.object = get_object_or_404(
            Donor,
            id=id,
            lot_id=pk
        )
        context = super().get_context_data(**kwargs)
        context["donor"] = self.object
        context["devices"] = self.get_devices()
        return context

    def get_devices(self):
        chids = self.object.lot.devicelot_set.all().values_list(
            "device_id", flat=True
        ).distinct()

        props = SystemProperty.objects.filter(
            owner=self.request.user.institution,
            value__in=chids
        ).order_by("-created")

        chids_ordered = []
        for x in props:
            if x.value not in chids_ordered:
                chids_ordered.append(Device(id=x.value))

        return chids_ordered


class AcceptDonorView(TemplateView):
    template_name = "donor_web.html"

    def get(self, *args, **kwargs):
        super().get(*args, **kwargs)
        self.success_url = reverse_lazy('lot:web_donor', args=[pk, id])
        pk = self.kwargs.get('pk')
        id = self.kwargs.get('id')

        self.object = get_object_or_404(
            Donor,
            id=id,
            lot_id=pk
        )
        self.object.reconciliation = True
        self.object.save()
        # TODO
        # self.send_email()

        return redirect(self.success_url)
