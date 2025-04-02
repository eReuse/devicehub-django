from django.db import IntegrityError
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, redirect, Http404, render
from django.contrib import messages
from django.core.cache import cache
from django.utils.translation import gettext_lazy as _
from django.db.models import Q, Count, Case, When, IntegerField
from django.views.generic.base import TemplateView
from django.forms import modelformset_factory, Select
from django.views.generic.edit import (
    CreateView,
    DeleteView,
    UpdateView,
    FormView,
)
from django_tables2 import SingleTableView
from dashboard.mixins import DashboardView
from lot.tables import LotTable
from evidence.models import SystemProperty
from device.models import Device
from lot.tables import LotTable
from lot.forms import (
    LotsForm,
    LotSubscriptionForm,
    AddDonorForm,
    BeneficiaryForm,
    PlaceReturnDeviceForm,
    SelectFormSet
)
from lot.models import (
    Lot,
    LotTag,
    LotProperty,
    LotSubscription,
    Beneficiary,
    Donor,
    DeviceBeneficiary
)
from dhemail.views import SubscriptionEmail

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
        self.success_url = reverse_lazy('dashboard:properties', args=[pk])
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


class SubscriptLotView(DashboardView, SubscriptionEmail, FormView):
    template_name = "subscription.html"
    title = _("Subscription")
    breadcrumb = "Lot / Subscription"
    form_class = LotSubscriptionForm
    lot = None

    def get_context_data(self, **kwargs):
        self.pk = self.kwargs.get('pk')
        context = super().get_context_data(**kwargs)
        self.get_lot()
        subscriptors = LotSubscription.objects.filter(lot=self.lot)
        user_subscripted = subscriptors.filter(user=self.request.user).first()

        if not self.request.user.is_admin and not user_subscripted:
            subscriptors = []

        context.update({
            'lot': self.lot,
            'subscriptors': subscriptors,
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

    def form_valid(self, form):
        form.save()
        self.template_subscriptor(form)
        self.send_email(form._user)
        response = super().form_valid(form)
        return response


class UnsubscriptLotView(DashboardView, TemplateView):

    def get(self, *args, **kwargs):
        super().get(*args, **kwargs)
        pk = self.kwargs.get('pk')
        id = self.kwargs.get('id')
        self.success_url = reverse_lazy('lot:subscription', args=[pk])

        self.object = get_object_or_404(
            LotSubscription,
            lot_id=pk,
            id=id
        )

        if self.object.user == self.request.user or self.request.user.is_admin:
            self.object.delete()
            # TODO
            # self.send_email()

        return redirect(self.success_url)


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
            type=LotSubscription.Type.CIRCUIT_MANAGER,
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
        #self.send_email(form._user)
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


class WebMixing(TemplateView):
    object = None

    def get_object(self):
        if self.object:
            return

        pk = self.kwargs.get('pk')
        id = self.kwargs.get('id')

        self.object = get_object_or_404(
            self.model,
            id=id,
            lot_id=pk
        )

    def get_context_data(self, **kwargs):
        self.get_object()
        context = super().get_context_data(**kwargs)
        context["object"] = self.object
        context["devices"] = self.get_devices()
        return context

    def get_devices(self):
        chids = self.get_chids()

        props = SystemProperty.objects.filter(
            owner=self.request.user.institution,
            value__in=chids
        ).order_by("-created")

        chids_ordered = []
        for x in props:
            if x.value not in chids_ordered:
                chids_ordered.append(x.value)

        return [Device(id=x, lot=self.object.lot) for x in chids_ordered]


class DonorView(WebMixing):
    template_name = "donor_web.html"
    model = Donor

    def get_chids(self):
        return self.object.lot.devicelot_set.all().values_list(
            "device_id", flat=True
        ).distinct()


class AcceptDonorView(TemplateView):
    template_name = "donor_web.html"

    def get(self, *args, **kwargs):
        super().get(*args, **kwargs)
        pk = self.kwargs.get('pk')
        id = self.kwargs.get('id')
        self.success_url = reverse_lazy('lot:web_donor', args=[pk, id])

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


class BeneficiaryView(DashboardView, FormView):
    template_name = "beneficiaries.html"
    title = _("Beneficiaries")
    breadcrumb = "Lot / Beneficiary"
    form_class = BeneficiaryForm
    lot = None

    def get_context_data(self, **kwargs):
        self.pk = self.kwargs.get('pk')
        context = super().get_context_data(**kwargs)
        self.get_lot()

        self.is_shop = LotSubscription.objects.filter(
            lot=self.lot,
            user=self.request.user,
            type=LotSubscription.Type.SHOP
        ).first()

        beneficiaries = []
        if self.request.user.is_admin or self.is_shop:
            if self.is_shop:
                beneficiaries = self.is_shop.beneficiary_set.filter(lot=self.lot)
            else:
                beneficiaries = Beneficiary.objects.filter(lot=self.lot)

        context.update({
            'lot': self.lot,
            'beneficiaries': beneficiaries,
            "action": _("Add")
        })
        return context

    def get_form_kwargs(self):
        self.pk = self.kwargs.get('pk')
        self.success_url = reverse_lazy('lot:beneficiary', args=[self.pk])

        self.is_shop = LotSubscription.objects.filter(
            lot_id=self.pk,
            user=self.request.user,
            type=LotSubscription.Type.SHOP
        ).first()

        kwargs = super().get_form_kwargs()
        kwargs["shop"] = self.is_shop
        kwargs["lot_pk"] = self.pk
        return kwargs

    def get_lot(self):
        self.lot = get_object_or_404(
            Lot,
            owner=self.request.user.institution,
            id=self.pk
        )

    def form_valid(self, form):
        form.devices = self.get_session_devices()
        form.save()
        response = super().form_valid(form)
        return response


class DeleteBeneficiaryView(DashboardView, TemplateView):

    def get(self, *args, **kwargs):
        super().get(*args, **kwargs)
        pk = self.kwargs.get('pk')
        id = self.kwargs.get('id')
        self.success_url = reverse_lazy('lot:beneficiary', args=[pk])

        self.object = get_object_or_404(
            Beneficiary,
            lot_id=pk,
            id=id
        )

        subscriptor = LotSubscription.objects.filter(
            type=LotSubscription.Type.SHOP,
            lot_id=pk,
            user=self.request.user
        ).first()

        if subscriptor or self.request.user.is_admin:
            self.object.delete()
            # TODO
            # self.send_email()

        return redirect(self.success_url)


class ListDevicesBeneficiaryView(DashboardView, FormView):
    template_name = "beneficiaries_devices.html"
    title = _("Beneficiaries")
    breadcrumb = "Lot / Beneficiary / Devices"

    def get_form_class(self):
        return modelformset_factory(
            DeviceBeneficiary,
            fields=["status"],
            widgets={"status": Select(attrs={"class": "form-select"})},
            labels={"status": ""},
            extra=0
        )

    def get_form(self):
        form_class = self.get_form_class()
        formset = form_class(**self.get_form_kwargs())

        for f in formset:
            f.device = Device(id=f.instance.device_id)

        return formset

    def get_form_kwargs(self):
        self.pk = self.kwargs.get('pk')
        self.id = self.kwargs.get('id')
        kwargs = super().get_form_kwargs()

        self.success_url = reverse_lazy(
            'lot:devices_beneficiary',
            args=[self.pk, self.id]
        )

        self.beneficiary = get_object_or_404(
            Beneficiary,
            lot_id=self.pk,
            id=self.id
        )

        kwargs["queryset"] = self.beneficiary.devicebeneficiary_set.filter()
        return kwargs

    def get_context_data(self, **kwargs):
        self.pk = self.kwargs.get('pk')
        self.id = self.kwargs.get('id')
        self.get_lot()

        context = super().get_context_data(**kwargs)
        self.is_shop = LotSubscription.objects.filter(
            lot=self.lot,
            user=self.request.user,
            type=LotSubscription.Type.SHOP
        ).first()

        if not self.request.user.is_admin and not self.is_shop:
            raise Http404

        if not self.request.user.is_admin and self.beneficiary.shop != self.is_shop:
            raise Http404

        new_devices = self.request.session.get("devices")
        devices = len(context.get("form", []))
        returned = self.beneficiary.devicebeneficiary_set.filter(
            status=DeviceBeneficiary.Status.RETURNED
        ).first()

        context.update({
            'lot': self.lot,
            'beneficiary': self.beneficiary,
            'new_devices': new_devices,
            'devices': devices,
            'returned': returned
        })

        return context

    def get_lot(self):
        self.lot = get_object_or_404(
            Lot,
            owner=self.request.user.institution,
            id=self.pk
        )

    def form_valid(self, form):
        form.save()
        response = super().form_valid(form)
        # TODO
        # self.send_email()
        return response


class DelDeviceBeneficiaryView(DashboardView, TemplateView):

    def get(self, *args, **kwargs):
        super().get(*args, **kwargs)
        pk = self.kwargs.get('pk')
        id = self.kwargs.get('id')
        dev_id = self.kwargs.get('dev_id')
        self.success_url = reverse_lazy('lot:devices_beneficiary', args=[pk, id])

        subscriptor = LotSubscription.objects.filter(
            type=LotSubscription.Type.SHOP,
            lot_id=pk,
            user=self.request.user
        ).first()

        device = DeviceBeneficiary.objects.filter(
            beneficiary_id=id,
            device_id=dev_id
        ).first()

        if subscriptor or self.request.user.is_admin:
            if device:
                device.delete()
            # TODO
            # self.send_email()

        return redirect(self.success_url)


class AddDevicesBeneficiaryView(DashboardView, TemplateView):

    def get(self, *args, **kwargs):
        super().get(*args, **kwargs)
        pk = self.kwargs.get('pk')
        id = self.kwargs.get('id')
        self.success_url = reverse_lazy('lot:devices_beneficiary', args=[pk, id])

        subscriptor = LotSubscription.objects.filter(
            type=LotSubscription.Type.SHOP,
            lot_id=pk,
            user=self.request.user
        ).first()

        beneficiary = get_object_or_404(
            Beneficiary,
            lot_id=pk,
            id=id
        )

        if subscriptor or self.request.user.is_admin:
            for dev in self.get_session_devices():
                beneficiary.add(dev.id)

            # TODO
            # self.send_email()

        return redirect(self.success_url)


class WebBeneficiaryView(WebMixing, FormView):
    template_name = "beneficiary_web.html"
    model = Beneficiary
    form_class = PlaceReturnDeviceForm

    def get_chids(self):
        return self.object.devicebeneficiary_set.all().values_list(
            "device_id", flat=True
        ).distinct()

    def get_formset(self):
        self.get_object()
        self.pk = self.kwargs.get('pk')
        self.id = self.kwargs.get('id')
        self.success_url = reverse_lazy(
            'lot:web_beneficiary',
            args=[self.pk, self.id]
        )
        devices = self.object.devicebeneficiary_set.filter(
            status=DeviceBeneficiary.Status.DELIVERED
        )
        initial_data = []
        for dev in devices:
            initial_data.append(
                {'id': dev.id, 'device_id': dev.device_id, 'returned': False}
            )
        return SelectFormSet(self.request.POST or None, initial=initial_data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        formset = self.get_formset()

        for f in formset:
            for dev in context.get("devices", []):
                if f.initial.get("device_id") == dev.id:
                    dev.form = f
                    break


        context["formset"] = formset
        context["count_returned"] = len(formset)
        return context

    def form_valid(self, form):
        formset = self.get_formset()

        if formset.is_valid():
            place = form.cleaned_data["place"]
            devices_returned = []
            for f in formset:
                if f.cleaned_data["returned"]:
                    devices_returned.append(f.cleaned_data["id"])

            for dev in self.object.devicebeneficiary_set.filter(id__in=devices_returned):
                dev.returned_place = place
                dev.status = DeviceBeneficiary.Status.RETURNED
                dev.save()

            # TODO
            # self.send_email()

            return super().form_valid(form)

        return self.render_to_response(self.get_context_data(form=form))


class AgreementBeneficiaryView(TemplateView):
    template_name = "beneficiary_agreement.html"

    def get_context_data(self, **kwargs):
        self.pk = self.kwargs.get('pk')
        self.id = self.kwargs.get('id')
        context = super().get_context_data(**kwargs)

        beneficiary = get_object_or_404(
            Beneficiary,
            lot_id=self.pk,
            id=self.id
        )

        context.update({
            'object': beneficiary,
        })
        return context


class AcceptBeneficiaryView(TemplateView):
    template_name = "beneficiary_agreement.html"

    def get(self, *args, **kwargs):
        super().get(*args, **kwargs)
        pk = self.kwargs.get('pk')
        id = self.kwargs.get('id')
        self.success_url = reverse_lazy('lot:web_beneficiary', args=[pk, id])

        self.object = get_object_or_404(
            Beneficiary,
            id=id,
            lot_id=pk
        )
        self.object.sign_conditions = True
        self.object.save()
        # TODO
        # self.send_email()

        return redirect(self.success_url)
