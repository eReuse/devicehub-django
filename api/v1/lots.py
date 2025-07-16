import json
import logging

from ninja import Router
from ninja.errors import HttpError
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

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
        400: MessageOut,     # Bad request
        401: MessageOut,     # Archived lot
        404: MessageOut,     # Lot not found
        422: MessageOut      # No valid devices
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
