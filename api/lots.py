import json
import logging

from ninja import NinjaAPI
from ninja.errors import HttpError
from ninja import Redoc

from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from ninja import NinjaAPI

from django.http import JsonResponse
from utils.save_snapshots import move_json, save_in_disk
from lot.models import Lot
from device.models import Device
from api.auth import GlobalAuth

logger = logging.getLogger('django')

api = NinjaAPI(auth=GlobalAuth())


# Response Schemas
class DeviceResponse(BaseModel):
    ID: str = Field(..., description="Unique device identifier", example="0FCDC8")
    manufacturer: str = Field(..., description="Device manufacturer", example="BANGHO")
    model: str = Field(..., description="Device model", example="BES G0304")
    serial: str = Field(..., description="Device serial number", example="0800789501001027")
    cpu_model: str = Field(..., description="CPU model", example="Intel Core i5-4340M")
    cpu_cores: int = Field(..., description="Number of CPU cores", example=2)
    ram_total: str = Field(..., description="Total RAM capacity", example="3.72 GiB")
    ram_type: str = Field(..., description="RAM type", example="DDR3")
    ram_slots: int = Field(..., description="Total RAM slots", example=4)
    slots_used: int = Field(..., description="Used RAM slots", example=2)
    drive: str = Field(..., description="Storage drive information", example="HTS545050A7E380 (465.76 GiB)")
    gpu_model: str = Field(..., description="GPU model", example="Intel 4th Gen Core Processor Integrated Graphics")
    type: str = Field(..., description="Device type", example="Laptop")
    user_properties: str = Field(..., description="Custom user properties", example="(invoice_code:pepe2) (invoice_code2:asd)")
    current_state: str = Field(..., description="Current device state")
    last_updated: datetime = Field(..., description="Last update timestamp", example="2025-07-02T21:21:13.626")

class LotInfo(BaseModel):
    id: int = Field(..., description="Unique identifier of the lot", example=1)
    name: str = Field(..., description="Name of the lot", example="donante-orgA")
    description: Optional[str] = Field(None, description="Description of the lot")

class LotDevicesResponse(BaseModel):
    lot: LotInfo
    devices: List[DeviceResponse]

class MessageOut(BaseModel):
    error: str = Field(..., description="Error message", example="Lot not found")

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

@api.get(
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
