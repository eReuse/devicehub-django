import logging

import math
from ninja import Router, Query
from ninja.errors import HttpError
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from lot.models import DeviceLot
from evidence.models import UserProperty
from api.auth import GlobalAuth
from api.v1.schemas import DeviceIDInput, LotDevicesResponse, MessageOut, OperationResult

from api.v1.utils import find_lot, check_valid_ids, get_all_search_results, build_device_response_list
from device.models import ProductCache

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
def retrieveLotDevices(
    request,
    lot_id: str,
    q: str = Query(None, description="Optional search query (ShortID or Text)"),
    prop_key: str = Query(None, description="Filter by UserProperty key"),
    prop_value: str = Query(None, description="Filter by UserProperty value"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(50, ge=1, le=50, description="Items per page")
):
    user = request.auth
    institution = user.institution

    lot = find_lot(lot_id, institution)
    if not lot:
        raise HttpError(404, "Lot not found for your institution")

    valid_ids_set = set(lot.devicelot_set.values_list("device_id", flat=True))

    # apply filters
    if prop_key or prop_value:
        prop_qs = UserProperty.objects.filter(owner=institution, device_id__in=valid_ids_set, type=UserProperty.Type.USER)
        if prop_key: prop_qs = prop_qs.filter(key=prop_key)
        if prop_value: prop_qs = prop_qs.filter(value=prop_value)
        valid_ids_set = valid_ids_set.intersection(prop_qs.values_list("device_id", flat=True))

    if q and q.strip():
        search_ids = get_all_search_results(q.strip(), institution)
        chids_ordered = [x for x in search_ids if x in valid_ids_set]
    else:
        chids_ordered = list(ProductCache.objects.filter(root__in=valid_ids_set).order_by('-last_updated').values_list('root', flat=True))

    total_items = len(chids_ordered)
    total_pages = math.ceil(total_items / size) if total_items > 0 else 1

    if total_items == 0 or page > total_pages:
        return LotDevicesResponse(
            lot={"id": lot.pk, "name": lot.name, "code": lot.code, "archived": lot.archived, "created": lot.created, "updated": lot.updated, "description": lot.description},
            pagination={"total_items": total_items, "total_pages": total_pages, "current_page": page, "page_size": size},
            devices=[]
        )

    # slice and then fetch data
    offset = (page - 1) * size
    chids_page = chids_ordered[offset : offset + size]

    devices_export = build_device_response_list(chids_page, institution, lot)

    return LotDevicesResponse(
        lot={"id": lot.pk, "name": lot.name, "code": lot.code, "archived": lot.archived, "created": lot.created, "updated": lot.updated, "description": lot.description},
        pagination={"total_items": total_items, "total_pages": total_pages, "current_page": page, "page_size": size},
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

    if not lot: raise HttpError(404, "Lot not found")
    if lot.archived: raise HttpError(401, "Lot is archived")

    try:
        valid_ids, invalid_ids = check_valid_ids(data.device_ids, user.institution)
        if not valid_ids: raise HttpError(422, "No valid device IDs provided")

        existing_devices = set(lot.devicelot_set.filter(device_id__in=valid_ids).values_list('device_id', flat=True))
        unassigned_ids = valid_ids - existing_devices

        if unassigned_ids:
            DeviceLot.objects.bulk_create([DeviceLot(lot=lot, device_id=did) for did in unassigned_ids], ignore_conflicts=True)

        return (200 if not invalid_ids else 207), OperationResult(
            success=True, processed_ids=list(valid_ids), invalid_ids=list(invalid_ids),
            message="Some id's were invalid" if invalid_ids else "All devices assigned successfully"
        )
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

    if not lot: raise HttpError(404, "Lot not found")

    try:
        valid_ids, invalid_ids = check_valid_ids(data.device_ids, user.institution)
        if not valid_ids: raise HttpError(422, "No valid device IDs provided")

        existing_devices = set(lot.devicelot_set.filter(device_id__in=valid_ids).values_list('device_id', flat=True))
        devices_to_remove = valid_ids & existing_devices

        if devices_to_remove:
            lot.devicelot_set.filter(device_id__in=devices_to_remove).delete()

        return (200 if not invalid_ids else 207), OperationResult(
            success=True, processed_ids=list(valid_ids), invalid_ids=list(invalid_ids),
            message="Some id's were invalid" if invalid_ids else "All devices de-assigned successfully"
        )
    except ValidationError as e:
        raise HttpError(400, str(e))
