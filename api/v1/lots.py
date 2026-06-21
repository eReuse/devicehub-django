import logging

from ninja import Router
from ninja.errors import HttpError
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from lot.models import DeviceLot
from device.models import Device, ProductCache
from api.auth import GlobalAuth
from api.v1.schemas import DeviceIDInput, LotDevicesResponse, MessageOut, OperationResult

from api.v1.utils import find_lot, check_valid_ids, build_device_export_dict

logger = logging.getLogger('django')
router = Router(tags=["Lots"])

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

    lot = find_lot(lot_id, user.institution)
    if not lot:
        raise HttpError(404, "Lot not found")

    chids = lot.devicelot_set.values_list("device_id", flat=True).distinct()
    cached_devices = ProductCache.objects.filter(owner=user.institution, root__in=chids)

    devices_export = []
    for cache in cached_devices:
        device = Device(id=cache.root, owner=user.institution)
        dev_data = build_device_export_dict(cache, device)
        devices_export.append(dev_data)

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
        devices=devices_export
    )

@router.post(
    "/{lot_id}/devices/",
    response={200: OperationResult, 207: OperationResult, 400: MessageOut, 401: MessageOut, 404: MessageOut, 422: MessageOut},
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
def assignLotDevices(request, lot_id: str, data: DeviceIDInput):
    user = request.auth
    lot = find_lot(lot_id, user.institution)

    if not lot:
        raise HttpError(404, "Lot not found")
    if lot.archived:
        raise HttpError(401, "Lot is archived")

    try:
        valid_ids, invalid_ids = check_valid_ids(data.device_ids, user.institution)
        if not valid_ids:
            raise HttpError(422, "No valid device IDs provided")

        existing_devices = set(lot.devicelot_set.filter(device_id__in=valid_ids).values_list('device_id', flat=True))
        unassigned_ids = valid_ids - existing_devices

        if unassigned_ids:
            DeviceLot.objects.bulk_create([
                DeviceLot(lot=lot, device_id=device_id) for device_id in unassigned_ids
            ], ignore_conflicts=True)

        response = OperationResult(
            success=True,
            processed_ids=list(valid_ids),
            invalid_ids=list(invalid_ids),
            message="Some id's were invalid" if invalid_ids else "All devices assigned successfully"
        )
        return 200 if not invalid_ids else 207, response

    except ValidationError as e:
        raise HttpError(400, str(e))

@router.delete(
    "/{lot_id}/devices/",
    response={200: OperationResult, 207: OperationResult, 400: MessageOut, 404: MessageOut, 422: MessageOut},
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
    lot = find_lot(lot_id, user.institution)

    if not lot:
        raise HttpError(404, "Lot not found")

    try:
        valid_ids, invalid_ids = check_valid_ids(data.device_ids, user.institution)
        if not valid_ids:
            raise HttpError(422, "No valid device IDs provided")

        existing_devices = set(lot.devicelot_set.filter(device_id__in=valid_ids).values_list('device_id', flat=True))
        devices_to_remove = valid_ids & existing_devices

        if devices_to_remove:
            lot.devicelot_set.filter(device_id__in=devices_to_remove).delete()

        response = OperationResult(
            success=True,
            processed_ids=list(valid_ids),
            invalid_ids=list(invalid_ids),
            message="Some id's were invalid" if invalid_ids else "All devices de-assigned successfully"
        )
        return 200 if not invalid_ids else 207, response

    except ValidationError as e:
        raise HttpError(400, str(e))
