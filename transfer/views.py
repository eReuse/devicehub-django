import json
import logging

from django.contrib import messages
from django.db import IntegrityError
from django.urls import reverse_lazy
from django.views.generic.edit import FormView
from django.shortcuts import get_object_or_404, Http404
from django.utils.translation import gettext_lazy as _
from django_tables2 import SingleTableView
from django.views.generic.base import TemplateView
from django.views.generic.edit import (
    CreateView,
    UpdateView,
    DeleteView,
)

from environmental_impact.algorithms.algorithm_factory import FactoryEnvironmentImpactAlgorithm as Feia
from dashboard.mixins import DashboardView
from action.models import StateDefinition, State, DeviceLog, Note
from device.views import DeviceLogMixin, DeleteUserPropertyView, UpdateUserPropertyView
from lot.models import Lot, LotTag
from device.models import Device
from evidence.models import Evidence, UserProperty
from transfer.models import Transfer
from transfer.forms import TransferForm
from transfer.tables import TransferTable, DeviceTable


logger = logging.getLogger(__name__)


class TransferTagMixing(DashboardView, SingleTableView):
    template_name = "transfers.html"
    title = _("Transfers")
    breadcrumb = _("transfers") + " / "
    success_url = reverse_lazy('dashboard:unassigned')
    model = Transfer
    table_class = TransferTable
    paginate_by = 10

    def get_queryset(self):
        return self.model.objects.filter(owner=self.request.user.institution)

    def get_context_data(self, **kwargs):
        self.get_queryset()
        context = super().get_context_data(**kwargs)
        context.update({
            'title': self.title,
            'breadcrumb': self.breadcrumb,
            'search_query': "",
        })
        return context

class TransferSendedView(TransferTagMixing):
    breadcrumb = _("transfers") + " / " + _("sended")

    def get_queryset(self):
        return self.model.objects.filter(
            owner=self.request.user.institution,
            type=self.model.Type.SENDED
        )


class TransferReceivedView(TransferTagMixing):
    breadcrumb = _("transfers") + " / " + _("received")

    def get_queryset(self):
        return self.model.objects.filter(
            owner=self.request.user.institution,
            type=self.model.Type.RECEIVED
        )


class TransferView(DashboardView, SingleTableView):
    template_name = "transfers.html"
    title = _("Transfer")
    breadcrumb = _("transfer") + " / "
    model = Transfer
    table_class = DeviceTable
    paginate_by = 10

    def get_queryset(self):
        self.object = get_object_or_404(
            self.model,
            owner=self.request.user.institution,
            id=self.kwargs.get("id")
        )
        return self.object.get_items()

    def get_context_data(self, **kwargs):
        self.get_queryset()
        context = super().get_context_data(**kwargs)
        context.update({
            'title': self.title,
            'breadcrumb': self.breadcrumb,
            'search_query': "",
            'path': 'tag',
        })
        return context


class NewTransferView(DashboardView, FormView):
    template_name = "transfer_lots.html"
    title = _("Transfer lot/s")
    breadcrumb = "transfer / new"
    success_url = reverse_lazy('dashboard:unassigned')
    form_class = TransferForm
    lots = []

    def get(self, request, *args, **kwargs):
        selected_ids = self.request.GET.getlist('select')
        if not selected_ids:
             messages.error(self.request, _("Not lots selected for transfer"))

        self.lots = Lot.objects.filter(
            id__in=selected_ids,
            owner=self.request.user.institution
        )
        for lot in self.lots:
            if lot.transfer:
                txt = _("Error lot {} have a transfer")
                messages.error(self.request, txt.format(lot.name))
        return super().get(request, *args, **kwargs)

    def get_success_url(self):
        return reverse_lazy('dashboard:unassigned')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'lots': self.lots,
            'lots_with_devices': any(lot.devices.exists() for lot in self.lots),
            'breadcrumb': self.breadcrumb,
            'title': self.title,
        })

        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        kwargs['website'] = "{}://{}".format(self.request.scheme, self.request.get_host())
        kwargs['initial']['selected_ids'] = self.request.GET.getlist('select') or []
        return kwargs

    def form_valid(self, form):
        form.save()

        if form.instance:
            messages.success(self.request, _("Lots succesfully transfer"))
        else:
            messages.error(self.request, _("Error signing transaction"))

        response = super().form_valid(form)
        return response

    def form_invalid(self, form):
        messages.error(self.request, _("Lots error transfer"))
        response = super().form_invalid(form)
        return response


class DeviceView(DashboardView, TemplateView):
    template_name = "details.html"
    title = _("Device")
    breadcrumb = "Device / Details"

    def get(self, request, *args, **kwargs):
        self.id = kwargs['id']
        self.pk = kwargs['pk']
        self.transfer = get_object_or_404(
            Transfer,
            owner=self.request.user.institution,
            id=self.kwargs.get("id")
        )

        self.object = self.get_device()
        if self.object and not self.object.last_evidence:
            raise Http404

        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.object.initial()
        lot_tags = LotTag.objects.filter(owner=self.request.user.institution)
        dpps = []
        try:
            enviromental_impact_algorithm = Feia.run_environmental_impact_calculation()
            enviromental_impact = enviromental_impact_algorithm.get_device_environmental_impact(
                self.object
            )
        except Exception as err:
            logger.error("Enviromental Impact: {}".format(err))
            enviromental_impact = None

        uuids = [self.object.uuid]
        state_definitions = StateDefinition.objects.filter(
            institution=self.request.user.institution
        ).order_by('order')
        device_states = State.objects.filter(snapshot_uuid__in=uuids).order_by('-date')
        device_logs = DeviceLog.objects.filter(
            snapshot_uuid__in=uuids).order_by('-date')
        device_notes = Note.objects.filter(snapshot_uuid__in=uuids).order_by('-date')
        self.object.lots = [self.transfer]

        context.update({
            'object': self.object,
            'snapshot': self.object.last_evidence,
            'lot_tags': lot_tags,
            'dpps': dpps,
            'impact': enviromental_impact,
            "state_definitions": state_definitions,
            "device_states": device_states,
            "device_logs": device_logs,
            "device_notes": device_notes,
            "transfer": self.transfer,
        })
        return context

    def get_device(self):
        evidences = self.transfer.get_evidences()

        try:
            self.object = Device(id=self.pk)
            doc = evidences[self.pk]
            uuid= doc.get("uuid")
            evi = Evidence(uuid, doc=doc)
            evi.owner = self.transfer.owner

            if not evi.is_legacy():
                evi.semi_parser()
            evi.get_time()
            self.object.last_evidence = evi
            self.object.uuid = uuid
            self.object.uuids = [uuid]
            self.transfer.name = self.transfer.destination_name
            self.transfer.code = ""
            self.transfer.description = ""
            self.object.owner = self.request.user.institution
            return self.object
        except Exception:
            return


class TransferAddUserPropertyView(DeviceLogMixin, CreateView):
    template_name = "new_user_property.html"
    title = _("New User Property")
    breadcrumb = "Device / New Property"
    model = UserProperty
    fields = ("key", "value")

    def form_valid(self, form):
        form.instance.owner = self.request.user.institution
        form.instance.user = self.request.user
        form.instance.uuid = self.property.uuid
        form.instance.type = UserProperty.Type.USER

        try:
            response = super().form_valid(form)
            messages.success(self.request, _("Property successfully added."))
            log_message = _("<Created> UserProperty: {}: {}".format(
                form.instance.key,
                form.instance.value
            ))

            self.log_registry(form.instance.uuid, log_message)
            return response
        except IntegrityError:
            messages.error(self.request, _("Property is already defined."))
            return self.form_invalid(form)

    def get_form_kwargs(self):
        self.id = self.kwargs['id']
        self.pk = self.kwargs['pk']
        self.transfer = get_object_or_404(
            Transfer,
            owner=self.request.user.institution,
            id=self.kwargs.get("id")
        )

        self.property = self.get_device()
        if not self.property:
            raise Http404

        self.property.transfer = self.transfer
        return super().get_form_kwargs()

    def get_success_url(self):
        return reverse_lazy('transfer:device', args=[self.id, self.pk]) + "#user_properties"

    def get_device(self):
        evidences = self.transfer.get_evidences()

        # try:
        self.property = Device(id=self.pk)
        doc = evidences[self.pk]
        uuid= doc.get("uuid")
        evi = Evidence(uuid, doc=doc)
        evi.owner = self.transfer.owner

        if not evi.is_legacy():
            evi.semi_parser()
        evi.get_time()
        self.property.last_evidence = evi
        self.property.uuid = uuid
        self.transfer.name = self.transfer.destination_name
        self.transfer.code = ""
        self.transfer.description = ""
        return self.property
        # except Exception:
        #     return

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["object"] = self.property
        context["transfer"] = self.transfer
        return context

class TransferDeleteUserPropertyView(DeleteUserPropertyView):

    def get_success_url(self):
        id = self.kwargs.get('id')
        pk = self.kwargs.get('device_id')
        return reverse_lazy('transfer:device', args=[id, pk]) + "#user_properties"

class TransferUpdateUserPropertyView(UpdateUserPropertyView):

    def get_success_url(self):
        id = self.kwargs.get('id')
        pk = self.kwargs.get('device_id')
        return reverse_lazy('transfer:device', args=[id, pk]) + "#user_properties"
