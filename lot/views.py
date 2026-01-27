import ast
import logging
import datetime

from django.db import IntegrityError
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, redirect, Http404, render
from django.contrib import messages
from django.core.cache import cache
from django.utils.translation import gettext_lazy as _
from django.db.models import Q, Count, Case, When, IntegerField
from django.views.generic.base import TemplateView, View
from django.forms import modelformset_factory, Select
from django.views.generic.edit import (
    CreateView,
    DeleteView,
    UpdateView,
    FormView,
)
from django_tables2 import SingleTableView
from dashboard.mixins import DashboardView
from environmental_impact.models import EnvironmentalImpact
from lot.tables import LotTable
from device.models import Device
from evidence.models import SystemProperty
from lot.tables import LotTable
from environmental_impact.algorithms.algorithm_factory import FactoryEnvironmentImpactAlgorithm
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
from dhemail.views import (
    NotifyEmail,
    SubscriptionEmail,
    DonorEmail,
    BeneficiaryAgreementEmail,
    BeneficiaryEmail,
)


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
        lots = Lot.objects.filter(owner=self.request.user.institution).order_by('-updated')
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

        sort = self.request.GET.get('sort', '-updated')
        return queryset.order_by(sort)


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


class DashboardLotMixing(DashboardView):
    lot = None

    def get_context_data(self, **kwargs):
        self.pk = kwargs.get('pk')
        context = super().get_context_data(**kwargs)
        self.get_lot()

        self.subscriptions = LotSubscription.objects.filter(
            lot=self.lot,
        )

        if not self.request.user.is_admin:
            self.subscriptions = self.subscriptions.filter(user=self.request.user)

        self.is_shop = self.subscriptions.filter(
            type=LotSubscription.Type.SHOP,
            user=self.request.user
        ).first()

        self.is_circuit_manager = self.subscriptions.filter(
            type=LotSubscription.Type.CIRCUIT_MANAGER,
            user=self.request.user
        ).first()

        beneficiaries = Beneficiary.objects.filter(lot=self.lot)
        donor = Donor.objects.filter(lot=self.lot).first()
        context.update({
            'lot': self.lot,
            'breadcrumb': self.breadcrumb,
            "title": "{} - {}".format(self.lot.name, self.title),
            'subscripted': self.subscriptions.first(),
            'is_circuit_manager': self.is_circuit_manager,
            'is_shop': self.is_shop,
            'donor': donor,
            'beneficiaries': beneficiaries,
            'subscriptions': self.subscriptions,
        })

        return context

    def get_lot(self):
        if self.lot:
            return

        self.lot = get_object_or_404(
            Lot,
            owner=self.request.user.institution,
            id=self.pk
        )


class LotPropertiesView(DashboardLotMixing, TemplateView):
    template_name = "properties.html"
    title = _("New Lot Property")
    breadcrumb = "Lot / New property"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        properties = LotProperty.objects.filter(
            lot=self.lot,
            owner=self.request.user.institution,
            type=LotProperty.Type.USER,
        )
        context.update({
            'properties': properties,
        })

        return context


class LotEnvironmentalImpactView(DashboardLotMixing, TemplateView):
    template_name = "lot_environmental_impact.html"
    title = _("Environmental Impact")
    breadcrumb = "Lot / Environmental Impact"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        device_ids = self.lot.devicelot_set.all().values_list(
            "device_id", flat=True
        ).distinct()
        devices = [Device(id=dev_id) for dev_id in device_ids]
        devices_with_evidence = [
            dev for dev in devices if dev.last_evidence
        ]
        env_impact = self._compute_environmental_impact(devices_with_evidence)
        context.update({
            'impact': env_impact,
            'device_count': len(devices),
            'devices_with_evidence': len(devices_with_evidence),
        })
        return context


    def _compute_environmental_impact(self, devices) -> EnvironmentalImpact:
        env_impact = None
        try:
            algorithm = (
                FactoryEnvironmentImpactAlgorithm
                .run_environmental_impact_calculation()
            )
            if devices:
                env_impact = algorithm.get_lot_environmental_impact(
                    devices
                )
                # Check if there's actual impact data
                if (env_impact and
                        env_impact.kg_CO2e.get('in_use', 0) == 0):
                    env_impact = None
        except Exception as err:
            logger.error(f"Lot Environmental Impact Error: {err}")
            env_impact = None

        return env_impact


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
        context["title"] = "{} - {}".format(self.title, self.lot.name)
        return context

    def get_success_url(self):
        return reverse_lazy("lot:properties", args=[self.lot.id])


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


class SubscriptLotView(DashboardLotMixing, SubscriptionEmail, FormView):
    template_name = "subscription.html"
    title = _("Subscription")
    breadcrumb = "Lot / Subscription"
    form_class = LotSubscriptionForm
    lot = None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        subscriptor = self.is_shop or self.is_circuit_manager
        if not self.request.user.is_admin and not subscriptor:
            self.subscriptions = []

        context.update({
            'lot': self.lot,
            'subscriptors': self.subscriptions,
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

    def get_success_url(self):
        return reverse_lazy("lot:subscription", args=[self.lot.id])


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


class ParticipantsView(DashboardLotMixing, TemplateView):
    template_name = "participants.html"
    title = _("Participants un this lot")
    breadcrumb = "Lot / Participants"


class DonorMixing(DashboardLotMixing, FormView):
    template_name = "donor.html"
    form_class = AddDonorForm
    lot = None
    donor = None

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
            kwargs["initial"] = {
                "name": self.donor.name,
                "email": self.donor.email,
                "address": self.donor.address
            }
            kwargs["donor"] = self.donor
        return kwargs



    def get_donor(self):
        if not self.lot:
            self.get_lot()

        self.donor = Donor.objects.filter(
            lot=self.lot,
        ).first()


class AddDonorView(DonorMixing, DonorEmail):
    title = _("Add Donor")
    breadcrumb = "Lot / {}".format(title)

    def form_valid(self, form):
        form.save()
        self.send_email(form.donor)
        response = super().form_valid(form)
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["action"] = _("Add")
        return context


class DelDonorView(DonorMixing):
    title = _("Donor")
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
        context["donor"] = self.object
        context["devices"] = self.get_devices()
        subscriptions = LotSubscription.objects.filter(
            lot=self.object.lot,
            user=self.request.user
        )
        shop = subscriptions.filter(type=LotSubscription.Type.SHOP).first()
        if shop:
            context["shop"] = shop

        cm = subscriptions.filter(type=LotSubscription.Type.CIRCUIT_MANAGER).first()
        if cm:
            context["circuit_manager"] = cm

        return context

    def get_devices(self):
        chids = self.get_chids()

        props = SystemProperty.objects.filter(
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


class AcceptDonorView(TemplateView, NotifyEmail):
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

        if self.object.accept_contract and self.object.reconciliation:
            return redirect(self.success_url)

        if not self.object.accept_contract:
            self.object.accept_contract = datetime.datetime.now()
        else:
            self.object.reconciliation = datetime.datetime.now()
        self.object.save()

        if self.object.accept_contract and self.object.reconciliation:
            self.get_templates_email()
            subscriptors = LotSubscription.objects.filter(
                lot_id=pk,
            )
            for s in subscriptors:
                self.send_email(s.user)

        return redirect(self.success_url)

    def get_templates_email(self):
        self.email_template_html = 'subscription/incoming_lot_ready_email.html'
        self.email_template = 'subscription/incoming_lot_ready_email.txt'
        self.email_template_subject = 'subscription/incoming_lot_ready_subject.txt'


class BeneficiaryView(DashboardLotMixing, BeneficiaryAgreementEmail, FormView):
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

        new_devices = {}
        for d in self.request.session.get("devices", []):
            d_ben = DeviceBeneficiary.objects.filter(
                device_id=d,
                beneficiary__lot=self.lot
            ).first()
            new_devices[d] = d_ben.beneficiary.email if d_ben else ''

        context.update({
            'lot': self.lot,
            'beneficiaries': beneficiaries,
            "action": _("Add"),
            "new_devices": new_devices.items()
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
        if self.lot:
            return

        self.lot = get_object_or_404(
            Lot,
            owner=self.request.user.institution,
            id=self.pk
        )

    def form_valid(self, form):
        form.devices = self.get_session_devices()
        form.save()
        self.beneficiary = form.ben
        self.send_email(form.ben)
        self.send_email_subscriptors()

        response = super().form_valid(form)
        return response

    def send_email_subscriptors(self):
        self.email_template_html = 'subscription/interest_beneficiary_email.html'
        self.email_template = 'subscription/interest_beneficiary_email.txt'
        self.email_template_subject = 'subscription/interest_beneficiary_subject.txt'
        self.get_lot()
        for c in self.lot.lotsubscription_set.filter():
            self.send_email(c.user)


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


class ListDevicesBeneficiaryView(DashboardLotMixing, BeneficiaryEmail, FormView):
    template_name = "beneficiaries_devices.html"
    title = _("Beneficiaries")
    breadcrumb = "Lot / Beneficiary / Devices"
    lot = None

    def get(self, *args, **kwargs):
        res = super().get(*args, **kwargs)
        if not self.beneficiary.devicebeneficiary_set.first():
            url = reverse_lazy("dashboard:lot", args=[self.beneficiary.lot.id])
            return redirect(url)

        return res

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
            choices = f.fields['status'].choices
            f.fields['status'].choices = choices[1:]

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

    def get_subscriptors(self):
        return LotSubscription.objects.filter(
            lot=self.lot,
        )

    def form_valid(self, form):
        form.save()
        response = super().form_valid(form)

        if form.changed_objects:
            devs_confirmed = []
            devs_delivered = []
            for ff in form.changed_objects:
                f = ff[0]
                if f.status == f.Status.CONFIRMED:
                    devs_confirmed.append(f.device_id)
                if f.status == f.Status.DELIVERED:
                    devs_delivered.append(f.device_id)

            if devs_confirmed:
                self.email_template_subject = 'beneficiary/confirm/subject.txt'
                self.email_template = 'beneficiary/confirm/email.txt'
                self.email_template_html = 'beneficiary/confirm/email.html'
                self.send_email(self.beneficiary)

                self.email_template_html = 'subscription/confirm_beneficiary_email.html'
                self.email_template = 'subscription/confirm_beneficiary_email.txt'
                self.email_template_subject = 'subscription/confirm_beneficiary_subject.txt'

                for c in self.get_subscriptors():
                    self.send_email(c.user)

            if devs_delivered:
                self.email_template_subject = 'beneficiary/delivery/subject.txt'
                self.email_template = 'beneficiary/delivery/email.txt'
                self.email_template_html = 'beneficiary/delivery/email.html'
                self.send_email(self.beneficiary)

                self.email_template_subject = 'beneficiary/return/subject.txt'
                self.email_template = 'beneficiary/return/email.txt'
                self.email_template_html = 'beneficiary/return/email.html'
                self.send_email(self.beneficiary)

                self.email_template_html = 'subscription/delivery_beneficiary_email.html'
                self.email_template = 'subscription/delivery_beneficiary_email.txt'
                self.email_template_subject = 'subscription/delivery_beneficiary_subject.txt'

                for c in self.get_subscriptors():
                    self.send_email(c.user)

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


class AddDevicesBeneficiaryView(DashboardView, NotifyEmail, TemplateView):

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

        self.beneficiary = get_object_or_404(
            Beneficiary,
            lot_id=pk,
            id=id
        )

        if subscriptor or self.request.user.is_admin:
            devices = self.request.session.get("devices", [])
            for dev in devices:
                exist = DeviceBeneficiary.objects.filter(device_id=dev).first()
                if exist:
                    messages.error(self.request, _("Device {} was already assigned to {}").format(
                        dev[:6].upper(), exist.beneficiary.email
                    ))
                else:
                    self.beneficiary.add(dev)

            self.request.session["devices"] = []
            self.send_email_subscriptors()


        return redirect(self.success_url)

    def send_email_subscriptors(self):
        self.email_template_html = 'subscription/interest_beneficiary_email.html'
        self.email_template = 'subscription/interest_beneficiary_email.txt'
        self.email_template_subject = 'subscription/interest_beneficiary_subject.txt'
        pk = self.kwargs.get('pk')
        if not pk:
            return

        subscriptors = LotSubscription.objects.filter(
            lot=self.beneficiary.lot,
        )

        for c in subscriptors:
            self.send_email(c.user)

    def get_email_context(self, user):
        context = super().get_email_context(user)
        context['beneficiary'] = self.beneficiary
        return context


class WebBeneficiaryView(WebMixing, FormView):
    template_name = "beneficiary_web.html"
    model = Beneficiary
    form_class = PlaceReturnDeviceForm

    def get(self, *args, **kwargs):
        res = super().get(*args, **kwargs)
        if not self.object.sign_conditions:
            url = reverse_lazy("lot:agreement_beneficiary", args=[
                self.object.lot.id, self.object.id])
            return redirect(url)

        return res

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
        self.beneficiary = self.object
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


class AcceptBeneficiaryView(TemplateView, NotifyEmail):
    template_name = "beneficiary_agreement.html"
    email_template_html = 'subscription/accept_conditions_beneficiary_email.html'
    email_template = 'subscription/accept_conditions_beneficiary_email.txt'
    email_template_subject = 'subscription/accept_conditions_beneficiary_subject.txt'

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
        self.object.sign_conditions = datetime.datetime.now()
        self.object.save()
        self.beneficiary = self.object
        self.send_email_subscriptors()

        return redirect(self.success_url)

    def send_email_subscriptors(self):

        subscriptors = LotSubscription.objects.filter(
            lot=self.beneficiary.lot,
        )

        for c in subscriptors:
            self.send_email(c.user)

    def get_email_context(self, user):
        context = super().get_email_context(user)
        context['beneficiary'] = self.beneficiary
        return context
