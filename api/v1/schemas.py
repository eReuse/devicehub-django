# api/v1/schemas.py
from pydantic import BaseModel, Field, validator
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext as _t

from lot.models import Lot
from typing import List, Optional
from ninja import ModelSchema
from datetime import datetime
from evidence.models import UserProperty

class DeviceResponse(BaseModel):
    ID: str = Field(
        ...,
        description=_("Unique device identifier (hash)"),
        example="2c0df789f17dbce47a605a5c8ccdf7bce112ecd667cabfd255e229999fc9ff24"
    )
    shortId: str = Field(
        ...,
        description=_("Unique device identifier, shortened")
        , example="0FCDC8"
    )
    manufacturer: str = Field(
        description=_("Manufacturer of the device"),
        example="BANGHO"
    )
    model: str = Field(
        description=_("Model name/number of the device"),
        example="BES G0304"
    )
    serial: str = Field(
        description=_("Serial number of the device"),
        example="0800789501001027"
    )
    cpu_model: str = Field(
        description=_("Processor model name"),
        example="Intel Core i5-4340M"
    )
    cpu_cores: int = Field(
        description=_("Number of CPU cores"),
        example=2
    )
    ram_total: str = Field(
        description=_("Total installed RAM memory"),
        example="3.72 GiB"
    )
    ram_type: str = Field(
        description=_("Type of RAM memory"),
        example="DDR3"
    )
    ram_slots: int = Field(
        description=_("Total available RAM slots"),
        example=4
    )
    slots_used: int = Field(
        description=_("Number of used RAM slots"),
        example=2
    )
    drive: str = Field(
        description=_("Storage drive model and capacity"),
        example="HTS545050A7E380 (465.76 GiB)"
    )
    gpu_model: str = Field(
        description=_("Graphics processing unit model"),
        example="Intel 4th Gen Core Processor Integrated Graphics"
    )
    type: str = Field(
        description=_("Type of device (desktop, laptop, etc.)"),
        example="Laptop"
    )
    user_properties: str = Field(
        description=_("Custom properties assigned to this device"),
        example="{'invoice_code': 'AKG12/7', 'to_be_sold': 'yes'}"
    )
    current_state: str = Field(
        description=_("Current state of the device"),
        example=_t("TO REPAIR")
    )
    last_updated: datetime = Field(
        description=_("Timestamp of last update to this record"),
        example="2025-07-02T21:21:13.626"
    )

class LotInfo(ModelSchema):
    class Meta:
        model = Lot
        fields = ['id', 'name', 'code', 'archived', 'created', 'updated', 'description']

    id: int = Field(
        ...,
        example=1,
        description=_("Unique identifier for the lot")
    )
    name: str = Field(
        ...,
        example="donante-orgA",
        description=_("Name of the lot")
    )
    code: Optional[str] = Field(
        description=_("Custom identification code assigned by operator"),
        example="INV-001AF"
    )
    archived: bool = Field(
        ...,
        example=False,
        description=_("Whether this lot has been archived")
    )
    description: Optional[str] = Field(
        example=_t("Contains April's inventory"),
        description=_("Description of the lot contents")
    )

class LotDevicesResponse(BaseModel):
    lot: LotInfo = Field(..., description=_("Lot information"))
    devices: List[DeviceResponse] = Field(..., description=_("List of devices in this lot"))

class MessageOut(BaseModel):
    error: Optional[str] = Field(
        None,
        description=_("Concise error message"),
        example=_t("Invalid JSON format")
    )
    details: Optional[str] = Field(
        None,
        description=_("Detailed error context"),
        example=_t("Could not parse the 'serial_number' field")
    )

class DeviceIDInput(BaseModel):
    device_ids: List[str] = Field(
        ...,
        min_length=1,
        description=_("List of device identifiers to process"),
        example=["0fcdc8469483f9520afae908fc933f618e8913122cb4fdc362a9f3fd6539ff2c"],
        title=_("Device IDs")
    )

    @validator('device_ids')
    def validate_device_ids(cls, v):
        if not all(isinstance(item, str) and item.strip() for item in v):
            raise ValueError(_("Device IDs must be non-empty strings"))
        return v

class OperationResult(BaseModel):
    success: bool = Field(
        ...,
        description=_("Overall operation status"),
        example=True
    )
    processed_ids: List[str] = Field(
        ...,
        description=_("Successfully processed device IDs"),
        example=["0fcdc8469483f9520afae908fc933f618e8913122cb4fdc362a9f3fd6539ff2c", "INVALID123"]
    )
    invalid_ids: List[str] = Field(
        default_factory=list,
        description=_("Invalid or unprocessable device IDs"),
        example=["INVALID123"]
    )
    message: Optional[str] = Field(
        None,
        description=_("Additional status information"),
        example=_t("Some devices were already processed")
    )

class PropertyIn(BaseModel):
    value: str = Field(
        ...,
        min_length=1,
        description=_("Property value to set"),
        example=_t("yes")
    )

class PropertyOut(ModelSchema):
    class Meta:
        model = UserProperty
        fields = ['key', 'value', 'created']

    device_id: str = Field(..., description=_("Associated device ID"))
    created: datetime = Field(
        ...,
        alias="created_at",
        description=_("When this property was created")
    )

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class SuccessResponse(BaseModel):
    status: str = Field(
        default="success",
        description=_("Operation status"),
        example="success"
    )
    property: PropertyOut = Field(..., description=_("User property information"))
    action: Optional[str] = Field(
        None,
        description=_("What action was performed"),
        example=_t("created")
    )

class SnapshotResponse(BaseModel):
    status: str = Field(
        ...,
        example="success",
        description=_("Operation status")
    )
    dhid: str = Field(
        ...,
        description=_("DeviceHub identifier (short code)"),
        example="0FCDC8"
    )
    url: str = Field(
        ...,
        description=_("Direct URL to access this device"),
        example="https://example.com/devices/0FCDC8/"
    )
    public_url: str = Field(
        ...,
        description=_("Public URL for sharing this device"),
        example="https://example.com/web/devices/0FCDC8/"
    )
