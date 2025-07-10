import json
import logging

from ninja import Router
from ninja.errors import HttpError

from django.http import JsonResponse
from utils.save_snapshots import move_json, save_in_disk
from lot.models import Lot
from device.models import Device
from api.auth import GlobalAuth
from api.v1.schemas import LotDevicesResponse, MessageOut

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

@router.get(
    "/lots/{lot_id}/",
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
def RetrieveLotDevices(request, lot_id: str):
    """
    Retrieve all devices belonging to a specific lot.

    Args:
        lot_id: Either the numeric ID or name of the lot to retrieve
    """
    owner = request.auth

    lot = _find_lot(lot_id, owner.institution)
    if not lot:
        raise HttpError(404, "Lot not found")

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

    return response_data
