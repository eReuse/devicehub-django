import json
import logging

from ninja import Router
from ninja.errors import HttpError
from django.core.exceptions import ValidationError

from evidence.models import SystemProperty
from lot.models import Lot
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

def _check_valid_ids(device_ids, owner):
    """
    Returns:
        valid_ids: a list of all valid device id's
        invalid_ids: self explanatory
    """
    properties = SystemProperty.objects.filter(
        owner = owner,
        value__in=device_ids
    ).values_list('value', flat=True)

    valid_ids = set(properties)
    invalid_ids = set(set(device_ids) - valid_ids)

    return valid_ids, invalid_ids


@router.get(
    "/{lot_id}/devices/",
    response={200: LotDevicesResponse, 404: MessageOut},
    summary="Retrieve devices in a lot",
    description="""Get all devices belonging to a specific lot.

    The lot can be identified by either:
    - Its numeric ID (e.g., #1)
    - Its name (e.g., "donante-orgA")

    Returns detailed information about the lot and all its devices.
    """,
    tags=["Lots"],
    auth=GlobalAuth(),
)
def retrieveLotDevices(request, lot_id: str):
    """
    Retrieve all devices belonging to a specific lot.

    Args:
        lot_id: Either the numeric ID or name of the lot to retrieve
    """
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
        400: MessageOut,     # Bad request
        404: MessageOut,     # Lot not found
        422: MessageOut      # No valid devices
    },
    summary="Assign devices in a lot",
    description="""Assign devices to a specified lot.

    The lot can be identified by either:
    - Its numeric ID (e.g., #1)
    - Its name (e.g., "donante-orgA")

    The input devices should be a list of Devicehub's device ids.
    """,
    tags=["Lots"],
    auth=GlobalAuth(),
)
def assignLotDevices(request, lot_id: str, data:DeviceIDInput):
    user = request.auth
    #TODO: allow assign to archived through api?, may with a flag
    lot = _find_lot(lot_id, user.institution)
    if not lot:
        raise HttpError(404, "Lot not found")

    try:
        valid_ids, invalid_ids = _check_valid_ids(data.device_ids, user.instution)
        if not valid_ids:
            raise HttpError(422, "No valid device IDs provided")

        existing_devices = set(lot.devicelot_set.filter(device_id__in=valid_ids)
                          .values_list('device_id', flat=True))

        unassigned_ids = set(valid_ids - existing_devices)

        for device_id in unassigned_ids:
            lot.add(device_id)

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
        400: MessageOut,        # Bad request
        404: MessageOut,        # Lot not found
        422: MessageOut         # No valid devices provided
    },
    summary="Remove devices from a lot",
    description="""Remove devices from a specified lot.

    Returns:
    - 200: All devices were successfully removed
    - 207: Partial removal (some devices invalid/not in lot)
    - 400: Invalid request data
    - 404: Lot not found
    - 422: No valid devices provided
    """,
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

        unassigned_ids = set(valid_ids - existing_devices)
        for device_id in unassigned_ids:
            lot.remove(device_id)

        response = OperationResult(
            success=True,
            processed_ids=valid_ids,
            invalid_ids=invalid_ids,
            message="Some id's were invalid" if invalid_ids  else "All devices de-assigned succesfuly"
        )
        return 200 if not invalid_ids else 207, response

    except ValidationError as e:
        raise HttpError(400, str(e))
