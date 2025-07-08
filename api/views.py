import json
import uuid
import logging

from uuid import uuid4

from django.urls import reverse_lazy
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django_tables2 import SingleTableView
from django.views.generic.edit import (
    CreateView,
    DeleteView,
    UpdateView,
)

from utils.save_snapshots import move_json, save_in_disk
from django.views.generic.edit import View
from dashboard.mixins import DashboardView
from evidence.models import SystemProperty, UserProperty
from evidence.parse_details import ParseSnapshot
from evidence.parse import Build
from device.models import Device
from api.models import Token
from user.tables import TokensTable


logger = logging.getLogger('django')


class ApiMixing(View):

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def auth(self):
        # Authentication
        auth_header = self.request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            logger.error("Invalid or missing token %s", auth_header)
            return JsonResponse({'error': 'Invalid or missing token'}, status=401)

        token = auth_header.split(' ')[1].strip("'").strip('"')
        try:
            uuid.UUID(token)
        except Exception:
            logger.error("Invalid or missing token %s", token)
            return JsonResponse({'error': 'Invalid or missing token'}, status=401)

        self.tk = Token.objects.filter(token=token).first()

        if not self.tk:
            logger.error("Invalid or missing token %s", token)
            return JsonResponse({'error': 'Invalid or missing token'}, status=401)


class NewSnapshotView(ApiMixing):

    def get(self, request, *args, **kwargs):
        return JsonResponse({}, status=404)

    def post(self, request, *args, **kwargs):
        response = self.auth()
        if response:
            return response

        # Validation snapshot
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            txt = "error: the snapshot is not a json"
            logger.error("%s", txt)
            return JsonResponse({'error': 'Invalid JSON'}, status=500)

        # Process snapshot
        path_name = save_in_disk(data, self.tk.owner.institution.name)

        # try:
        #     Build(data, None, check=True)
        # except Exception:
        #     return JsonResponse({'error': 'Invalid Snapshot'}, status=400)

        ev_uuid = data.get("uuid")
        if data.get("credentialSubject"):
            ev_uuid = data["credentialSubject"].get("uuid")

        if not ev_uuid:
            txt = "error: the snapshot does not have an uuid"
            logger.error("%s", txt)
            return JsonResponse({'status': txt}, status=500)

        exist_property = SystemProperty.objects.filter(
            uuid=ev_uuid
        ).first()

        if exist_property:
            txt = "error: the snapshot {} exist".format(ev_uuid)
            logger.warning("%s", txt)
            return JsonResponse({'status': txt}, status=500)


        try:
            Build(data, self.tk.owner)
        except Exception as err:
            if settings.DEBUG:
                logger.exception("%s", err)
            snapshot_id = ev_uuid
            txt = "It is not possible to parse snapshot: %s."
            logger.error(txt, snapshot_id)
            text = "fail: It is not possible to parse snapshot. {}".format(err)
            return JsonResponse({'status': text}, status=500)

        prop = SystemProperty.objects.filter(
            uuid=ev_uuid,
            # TODO this is hardcoded, it should select the user preferred algorithm
            key="ereuse24",
            owner=self.tk.owner.institution
        ).first()


        if not prop:
            logger.error("Error: No property  for uuid: %s", ev_uuid)
            return JsonResponse({'status': 'fail'}, status=500)

        url_args = reverse_lazy("device:details", args=(prop.value,))
        url = request.build_absolute_uri(url_args)

        response = {
            "status": "success",
            "dhid": prop.value[:6].upper(),
            "url": url,
            # TODO replace with public_url when available
            "public_url": url
        }
        move_json(path_name, self.tk.owner.institution.name)

        return JsonResponse(response, status=200)


class TokenView(DashboardView, SingleTableView):
    template_name = "token.html"
    title = _("Credential management")
    section = "Credential"
    subtitle = _('Managament Tokens')
    icon = 'bi bi-key'
    model = Token
    table_class = TokensTable

    def get_queryset(self):
        """
        Override the get_queryset method to filter events based on the user type.
        """
        return Token.objects.filter().order_by("-id")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'tokens': Token.objects.all(),
        })
        return context


class TokenDeleteView(DashboardView, DeleteView):
    model = Token

    def get(self, request, *args, **kwargs):
        self.pk = kwargs['pk']
        self.object = get_object_or_404(self.model, pk=self.pk, owner=self.request.user)
        self.object.delete()

        return redirect('api:tokens')


class TokenNewView(DashboardView, CreateView):
    template_name = "new_token.html"
    title = _("Credential management")
    section = "Credential"
    subtitle = _('New Tokens')
    icon = 'bi bi-key'
    model = Token
    success_url = reverse_lazy('api:tokens')
    fields = (
        "tag",
    )

    def form_valid(self, form):
        form.instance.owner = self.request.user
        form.instance.token = uuid4()
        return super().form_valid(form)


class EditTokenView(DashboardView, UpdateView):
    template_name = "new_token.html"
    title = _("Credential management")
    section = "Credential"
    subtitle = _('New Tokens')
    icon = 'bi bi-key'
    model = Token
    success_url = reverse_lazy('api:tokens')
    fields = (
        "tag",
    )

    def get_form_kwargs(self):
        pk = self.kwargs.get('pk')
        self.object = get_object_or_404(
            self.model,
            owner=self.request.user,
            pk=pk,
        )
        kwargs = super().get_form_kwargs()
        return kwargs


class DetailsDeviceView(ApiMixing):

    def get(self, request, *args, **kwargs):
        response = self.auth()
        if response:
            return response

        self.pk = kwargs['pk']
        self.object = Device(id=self.pk)

        if not self.object.last_evidence:
            return JsonResponse({}, status=404)

        if self.object.owner != self.tk.owner.institution:
            return JsonResponse({}, status=403)

        data = self.get_data()
        return JsonResponse(data, status=200)

    def post(self, request, *args, **kwargs):
        return JsonResponse({}, status=404)

    def get_data(self):
        data = {}
        self.object.initial()
        self.object.get_last_evidence()
        evidence = self.object.last_evidence

        if evidence.is_legacy():
            data.update({
                "device": evidence.get("device"),
                "components": evidence.get("components"),
            })
        else:
            evidence.get_doc()
            snapshot = ParseSnapshot(evidence.doc).snapshot_json
            data.update({
                "device": snapshot.get("device"),
                "components": snapshot.get("components"),
            })

        uuids = SystemProperty.objects.filter(
            owner=self.tk.owner.institution,
            value=self.pk
        ).values("uuid")

        properties = UserProperty.objects.filter(
            uuid__in=uuids,
            owner=self.tk.owner.institution,
        ).values_list("key", "value")

        data.update({"properties": list(properties)})
        return data


class AddPropertyView(ApiMixing):

    def post(self, request, *args, **kwargs):
        response = self.auth()
        if response:
            return response

        self.pk = kwargs['pk']
        institution = self.tk.owner.institution
        self.property = SystemProperty.objects.filter(
            owner=institution,
            value=self.pk,
        ).first()

        if not self.property:
            return JsonResponse({}, status=404)

        try:
            data = json.loads(request.body)
            key = data["key"]
            value = data["value"]
        except Exception:
            logger.error("Invalid Snapshot of user %s", self.tk.owner)
            return JsonResponse({'error': 'Invalid JSON'}, status=500)

        UserProperty.objects.create(
            uuid=self.property.uuid,
            owner=self.tk.owner.institution,
            key = key,
            value = value
        )

        return JsonResponse({"status": "success"}, status=200)

    def get(self, request, *args, **kwargs):
        return JsonResponse({}, status=404)


class LotDevicesAPIView(ApiMixing):

    def _find_lot(self, identifier):
        """ Find lot by either name:(str) or pk:(int) """
        try:
            if identifier.isdigit():
                return Lot.objects.get(
                    id=int(identifier),
                    owner=self._get_institution()
                )
            return Lot.objects.get(
                name=identifier,
                owner=self._get_institution()
            )
        except (BaseException) as e:
            logger.error(f"Invalid lot identifier: {identifier}")

        return None

    def _load_devices_payload(self, request):
        """
        Returns:
            devices_id: A list of all of the user supplied id's
            valid_devices: a list of all valid device id's
            invalid_ids: self explanatory
        Can propagate :
            ValidationError for empty list
        """
        body_data = json.loads(request.body)
        devices_id = body_data.get('devices', [])

        if not isinstance(devices_id, list):
            raise ValidationError("Devices must be provided as an array")
        if not devices_id:
            raise ValidationError("Empty devices list")

        properties = SystemProperty.objects.filter(
            value__in=devices_id
        ).values_list('value', flat=True)

        valid_id = [value for value in properties]
        invalid_ids = list(set(devices_id)-set(valid_id))

        if len(invalid_ids) == len(devices_id):
            raise ValidationError("None of the provided device IDs are valid")

        return devices_id, valid_id, invalid_ids

    def post(self, request, identifier ):
        if auth_response := self.auth():
            return auth_response

        lot = self._find_lot(identifier)
        if not lot:
            return JsonResponse(
                {'error': 'Lot not found or access denied'},
                status=404
            )

        try:
            all_ids, valid_ids, invalid_ids = self._load_devices_payload(request)
        except (ValidationError, json.JSONDecodeError) as e:
            return JsonResponse(
                {'error': str(e)},
                status=400
            )

        for dev in valid_ids:
            lot.add(dev)

        partial_failure = len(all_ids) != len(valid_ids)

        return JsonResponse(
            {
                "status": "assigned",
                "devices": valid_ids,
                "lot_id": lot.id,
                "lot_name": lot.name,
                "invalid_ids": invalid_ids
            },
            status=207 if partial_failure else 200
        )

    def delete(self, request, identifier):
        """Deletes devices associated with a lot"""

        if auth_response := self.auth():
            return auth_response

        lot = self._find_lot(identifier)
        if not lot:
            return JsonResponse(
                {'error': 'Lot not found or access denied'},
                status=404
            )

        try:
            all_ids, valid_ids, invalid_ids = self._load_devices_payload(request)
        except ValidationError as e:
            return JsonResponse({'error': str(e)}, status=400)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON format'}, status=400)

        for dev in valid_ids:
            lot.remove(dev)

        partial_failure = len(all_ids) != len(valid_ids)
        return JsonResponse(
            {
                "status": "deleted",
                "devices": valid_ids,
                "lot_id": lot.id,
                "lot_name": lot.name,
                "invalid_ids": invalid_ids
            },
            status=207 if partial_failure else 200
        )

    def get(self, request, identifier):
        if auth_response := self.auth():
            return auth_response

        lot = self._find_lot(identifier)
        if not lot:
            return JsonResponse(
                {'error': 'Lot not found or access denied'},
                status=404
            )

        # Fetch all devices_id
        chids = lot.devicelot_set.all().values_list(
            "device_id", flat=True
        ).distinct()
        devices = [Device(id=x) for x in chids]

        devices_data = [
            device.components_export()
            for device in devices
        ]

        response_data = {
            "lot": {
                "id": lot.id,
                "name": lot.name,
                "description": lot.description,
            },
            "devices": devices_data,
        }

        return JsonResponse(response_data, status=200)
