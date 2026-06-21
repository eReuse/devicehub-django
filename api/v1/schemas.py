from typing import List, Optional, Union, Dict
from datetime import datetime

from pydantic import BaseModel, Field, field_validator
from ninja import ModelSchema, Schema
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext as _t

from lot.models import Lot
from evidence.models import UserProperty


class DeviceResponse(BaseModel):
    ID: str = Field(
        ...,
        description=str(_("Unique device identifier (hash)")),
        example="2c0df789f17dbce47a605a5c8ccdf7bce112ecd667cabfd255e229999fc9ff24"
    )
    shortId: str = Field(
        ...,
        description=str(_("Unique device identifier, shortened")),
        example="0FCDC8"
    )
    type: str = Field(
        ...,
        description=str(_("Type of device (desktop, laptop, etc.)")),
        example="Laptop"
    )
    last_updated: datetime = Field(
        ...,
        description=str(_("Timestamp of last update to this record")),
        example="2025-07-02T21:21:13.626"
    )

    manufacturer: Optional[str] = Field(
        default=None,
        description=str(_("Manufacturer of the device")),
        example="BANGHO"
    )
    model: Optional[str] = Field(
        default=None,
        description=str(_("Model name/number of the device")),
        example="BES G0304"
    )
    serial: Optional[str] = Field(
        default=None,
        description=str(_("Serial number of the device")),
        example="0800789501001027"
    )
    cpu_model: Optional[str] = Field(
        default=None,
        description=str(_("Processor model name")),
        example="Intel Core i5-4340M"
    )
    cpu_cores: Optional[Union[int, str]] = Field(
        default=None,
        description=str(_("Number of CPU cores")),
        example=2
    )
    ram_total: Optional[Union[str, int, float]] = Field(
        default=None,
        description=str(_("Total installed RAM memory")),
        example="16"
    )
    ram_type: Optional[str] = Field(
        default=None,
        description=str(_("Type of RAM memory")),
        example="DDR3"
    )
    ram_slots: Optional[Union[int, str]] = Field(
        default=None,
        description=str(_("Total available RAM slots")),
        example=4
    )
    slots_used: Optional[Union[int, str]] = Field(
        default=None,
        description=str(_("Number of used RAM slots")),
        example=2
    )
    drive: Optional[str] = Field(
        default=None,
        description=str(_("Storage drive model and capacity")),
        example="HTS545050A7E380 (465.76 GiB)"
    )
    gpu_model: Optional[str] = Field(
        default=None,
        description=str(_("Graphics processing unit model")),
        example="Intel 4th Gen Core Processor Integrated Graphics"
    )
    user_properties: Optional[Dict[str, str]] = Field(
        default=None,
        description=str(_("Custom properties assigned to this device")),
        example=[{"invoice_code": "AKG12/7"}, {"to_be_sold": "yes"}]
    )
    current_state: Optional[str] = Field(
        default=None,
        description=str(_("Current state of the device")),
        example=str(_("TO REPAIR"))
    )

    model_config = {"extra": "allow"}


class LotInfo(ModelSchema):
    class Meta:
        model = Lot
        fields = ['id', 'name', 'code', 'archived', 'created', 'updated', 'description']

    id: int = Field(
        ...,
        example=1,
        description=str(_("Unique identifier for the lot"))
    )
    name: str = Field(
        ...,
        example="donante-orgA",
        description=str(_("Name of the lot"))
    )
    code: Optional[str] = Field(
        description=str(_("Custom identification code assigned by operator")),
        example="INV-001AF"
    )
    archived: bool = Field(
        ...,
        example=False,
        description=str(_("Whether this lot has been archived"))
    )
    description: Optional[str] = Field(
        example=str(_t("Contains April's inventory")),
        description=str(_("Description of the lot contents"))
    )


class LotDevicesResponse(BaseModel):
    lot: LotInfo = Field(..., description=str(_("Lot information")))
    devices: List[DeviceResponse] = Field(..., description=str(_("List of devices in this lot")))


class MessageOut(BaseModel):
    error: Optional[str] = Field(
        None,
        description=str(_("Concise error message")),
        example=str(_t("Invalid JSON format"))
    )
    details: Optional[str] = Field(
        None,
        description=str(_("Detailed error context")),
        example=str(_t("Could not parse the 'serial_number' field"))
    )


class DeviceIDInput(BaseModel):
    device_ids: List[str] = Field(
        ...,
        min_length=1,
        description=str(_("List of device identifiers to process")),
        example=["0fcdc8469483f9520afae908fc933f618e8913122cb4fdc362a9f3fd6539ff2c"],
        title=str(_("Device IDs"))
    )

    @field_validator('device_ids')
    @classmethod
    def validate_device_ids(cls, v):
        if not all(isinstance(item, str) and item.strip() for item in v):
            raise ValueError(str(_("Device IDs must be non-empty strings")))
        return v


class OperationResult(BaseModel):
    success: bool = Field(
        ...,
        description=str(_("Overall operation status")),
        example=True
    )
    processed_ids: List[str] = Field(
        ...,
        description=str(_("Successfully processed device IDs")),
        example=["0fcdc8469483f9520afae908fc933f618e8913122cb4fdc362a9f3fd6539ff2c", "INVALID123"]
    )
    invalid_ids: List[str] = Field(
        default_factory=list,
        description=str(_("Invalid or unprocessable device IDs")),
        example=["INVALID123"]
    )
    message: Optional[str] = Field(
        None,
        description=str(_("Additional status information")),
        example=str(_t("Some devices were already processed"))
    )


class PropertyIn(BaseModel):
    value: str = Field(
        ...,
        min_length=1,
        description=str(_("Property value to set")),
        example=str(_t("yes"))
    )


class PropertyOut(ModelSchema):
    class Meta:
        model = UserProperty
        fields = ['key', 'value', 'created']

    device_id: str = Field(..., description=str(_("Associated device ID")))
    created: datetime = Field(
        ...,
        validation_alias="created_at",  # V2 replacement for alias="created_at"
        serialization_alias="created_at",
        description=str(_("When this property was created"))
    )
    # Note: json_encoders removed as Pydantic V2 automatically formats datetimes to ISO.


class SuccessResponse(BaseModel):
    status: str = Field(
        default="success",
        description=str(_("Operation status")),
        example="success"
    )
    property: PropertyOut = Field(..., description=str(_("User property information")))
    action: Optional[str] = Field(
        None,
        description=str(_("What action was performed")),
        example=str(_t("created"))
    )


class SnapshotResponse(BaseModel):
    status: str = Field(
        ...,
        example="success",
        description=str(_("Operation status"))
    )
    dhid: str = Field(
        ...,
        description=str(_("DeviceHub identifier (short code)")),
        example="0FCDC8"
    )
    url: str = Field(
        ...,
        description=str(_("Direct URL to access this device")),
        example="https://example.com/devices/0FCDC8/"
    )
    public_url: str = Field(
        ...,
        description=str(_("Public URL for sharing this device")),
        example="https://example.com/web/devices/0FCDC8/"
    )


class DeviceLogOut(Schema):
    event: str = Field(
        ...,
        example="<Created> UserProperty: status: refurbished",
        description=str(_("Description of the event or action performed"))
    )
    date: datetime = Field(
        ...,
        example="2026-06-12T14:30:00Z",
        description=str(_("Timestamp when the event occurred"))
    )
    user: Optional[str] = Field(
        default=None,
        example="admin_user",
        description=str(_("Username of the person who triggered the event, or System if null"))
    )
    snapshot_uuid: str = Field(
        ...,
        example="123e4567-e89b-12d3-a456-426614174000",
        description=str(_("UUID of the associated hardware snapshot (evidence)"))
    )


class DeviceWithLogsOut(Schema):
    device: DeviceResponse = Field(
        ...,
        description=str(_("Complete device information including components and properties"))
    )
    logs: List[DeviceLogOut] = Field(
        ...,
        description=str(_("Chronological list of all events associated with this device"))
    )


class BulkPropertyIn(Schema):
    device_ids: List[str] = Field(
        ...,
        example=["ereuse24:50d7033117...", "0FCDC8"],
        description=str(_("List of device identifiers (can be full hashes, short IDs, or custom aliases)"))
    )
    key: str = Field(
        ...,
        example="warranty",
        description=str(_("The name or key of the user property to assign"))
    )
    value: str = Field(
        ...,
        example="12-months",
        description=str(_("The value to assign to the property across all specified devices"))
    )
