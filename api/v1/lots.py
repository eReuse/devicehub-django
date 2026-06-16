import json
import logging

from ninja import Router
from ninja.errors import HttpError
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from evidence.models import RootAlias
from lot.models import Lot, DeviceLot
from device.models import Device
from api.auth import GlobalAuth
from api.v1.schemas import DeviceIDInput, LotDevicesResponse, MessageOut, OperationResult

logger = logging.getLogger('django')

router = Router(tags=["Lots"])


def _find_lot(identifier, institution):
    """ Find lot by either name:(str) or pk:(int) """
    try:
        if identifier.isdigit():
            return Lot.objects.get(
                id=int(identifier),
                owner=institution
            )
        return Lot.objects.get(
            name=identifier,
            owner=institution
        )
    except (BaseException) as e:
        logger.error(f"Invalid lot identifier: {identifier}")
    return None

def _resolve_single_device(pk: str, owner):
    clean_pk = pk.split(":")[-1] if ":" in pk else pk
    base_qs = RootAlias.objects.filter(owner=owner)

    strategies = [
        base_qs.filter(alias__endswith=f":{clean_pk}")
    ]
    if len(clean_pk) >= 6:
        short_id = clean_pk[:6]
        strategies.append(base_qs.filter(alias__contains=f":{short_id}"))

    strategies.append(base_qs.filter(alias__icontains=clean_pk))

    for qs in strategies:
        count = qs.count()
        if count == 1:
            return qs.first().root
        elif count > 1:
            return None

    return None

def _check_valid_ids(device_ids, owner):
    valid_ids = set()
    invalid_ids = set()
    pending_ids = set(device_ids)

    exact_matches = RootAlias.objects.filter(owner=owner, alias__in=pending_ids)

    for match in exact_matches:
        valid_ids.add(match.root)
        pending_ids.remove(match.alias)

    for pk in pending_ids:
        canonical_id = _resolve_single_device(pk, owner)
        if canonical_id:
            valid_ids.add(canonical_id)
        else:
            invalid_ids.add(pk)

    return valid_ids, invalid_ids


@router.get(
    "/{lot_id}/devices/",
    response={200: LotDevicesResponse, 404: MessageOut},
    summary=_("Retrieve devices in a lot"),
    description=_("""Get all devices belonging to a specific lot.

    The lot can be identified by either:
    - Its numeric ID (e.g., #1)
    - Its name (e.g., "donante-orgA")

    Returns:
    - 200 - Lot details (ID, name, description, etc.) and list of all devices with their technical specifications
    - 404 - Lot not found
    """),
    tags=["Lots"],
    auth=GlobalAuth(),
)
def retrieveLotDevices(request, lot_id: str):
    user = request.auth

    lot = _find_lot(lot_id, user.institution)
    if not lot:
        raise HttpError(404, "Lot not found")

    # Fetch all devices_id
    chids = lot.devicelot_set.all().values_list(
        "device_id", flat=True
    ).distinct()
    devices = [Device(id=x) for x in chids]

    return LotDevicesResponse(
        lot={
            "id": lot.pk,
            "name": lot.name,
            "code": lot.code,
            "archived": lot.archived,
            "created": lot.created,
            "updated": lot.updated,
            "description": lot.description,
        },
        devices=[device.components_export() for device in devices]
    )


@router.post(
    "/{lot_id}/devices/",
    response={
        200: OperationResult,
        207: OperationResult,
        400: MessageOut,
        401: MessageOut,
        404: MessageOut,
        422: MessageOut
    },
    summary=_("Assign devices to lot"),
    description=_("""
    Add multiple devices to a specified lot in a single operation.

    The lot can be identified by either:
    - Its numeric ID (e.g., #1)
    - Its name (e.g., "donante-orgA")

    Returns:
    - 200: All valid devices assigned
    - 207: Partial assignment (some invalid IDs)
    - 401: Lot is archived
    - 404: Lot wasnot found
    - 422: No valid device IDs provided
    """),
    tags=["Lots"],
    auth=GlobalAuth(),
)
def assignLotDevices(request, lot_id: str, data:DeviceIDInput):
    user = request.auth
    lot = _find_lot(lot_id, user.institution)
    if not lot:
        raise HttpError(404, "Lot not found")
    if lot.archived:
        raise HttpError(401, "Lot is archived")
    try:
        valid_ids, invalid_ids = _check_valid_ids(data.device_ids, user.institution)
        if not valid_ids:
            raise HttpError(422, "No valid device IDs provided")

        existing_devices = set(lot.devicelot_set.filter(device_id__in=valid_ids)
                          .values_list('device_id', flat=True))

        unassigned_ids = set(valid_ids - existing_devices)

        if unassigned_ids:
            DeviceLot.objects.bulk_create([
                DeviceLot(lot=lot, device_id=device_id)
                for device_id in unassigned_ids
            ], ignore_conflicts=True)

        response = OperationResult(
            success=True,
            processed_ids=valid_ids,
            invalid_ids=invalid_ids,
            message="Some id's were invalid" if invalid_ids  else "All devices assigned succesfuly"
        )
        return 200 if not invalid_ids else 207, response

    except ValidationError as e:
        raise HttpError(400, str(e))

@router.delete(
    "/{lot_id}/devices/",
    response={
        200: OperationResult,
        207: OperationResult,
        400: MessageOut,
        404: MessageOut,
        422: MessageOut
    },
    summary=_("Remove devices from lot"),
    description=_("""
    Remove multiple devices from a specified lot in a single operation.

    The lot can be identified by either:
    - Its numeric ID (e.g., #1)
    - Its name (e.g., "donante-orgA")

    Returns:
    - 200: All valid devices removed
    - 207: Partial removal (some invalid IDs)
    - 422: No valid device IDs provided
    """),
    tags=["Lots"],
    auth=GlobalAuth()
)
def remove_devices_from_lot(request, lot_id: str, data: DeviceIDInput):
    user = request.auth
    lot = _find_lot(lot_id, user.institution)
    if not lot:
        raise HttpError(404, "Lot not found")

    try:
        valid_ids, invalid_ids = _check_valid_ids(data.device_ids, user.institution)
        if not valid_ids:
            raise HttpError(422, "No valid device IDs provided")

        existing_devices = set(lot.devicelot_set.filter(device_id__in=valid_ids)
                          .values_list('device_id', flat=True))

        devices_to_remove = list(valid_ids & existing_devices)
        if devices_to_remove:
            lot.devicelot_set.filter(device_id__in=devices_to_remove).delete()

        response = OperationResult(
            success=True,
            processed_ids=valid_ids,
            invalid_ids=invalid_ids,
            message="Some id's were invalid" if invalid_ids  else "All devices de-assigned succesfuly"
        )
        return 200 if not invalid_ids else 207, response

    except ValidationError as e:
        raise HttpError(400, str(e))
