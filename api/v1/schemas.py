# api/v1/schemas.py
from pydantic import BaseModel, Field, validator
from ninja.errors import ValidationError

from lot.models import Lot
from typing import List, Optional
from ninja import ModelSchema
from datetime import datetime
from evidence.models import UserProperty

class DeviceResponse(BaseModel):
    ID: str = Field(..., description="Unique device identifier", example="0FCDC8")
    manufacturer: str = Field(description="Device manufacturer", example="BANGHO")
    model: str = Field(description="Device model", example="BES G0304")
    serial: str = Field(description="Device serial number", example="0800789501001027")
    cpu_model: str = Field(description="CPU model", example="Intel Core i5-4340M")
    cpu_cores: int = Field(description="Number of CPU cores", example=2)
    ram_total: str = Field(description="Total RAM capacity", example="3.72 GiB")
    ram_type: str = Field(description="RAM type", example="DDR3")
    ram_slots: int = Field(description="Total RAM slots", example=4)
    slots_used: int = Field(description="Used RAM slots", example=2)
    drive: str = Field(description="Storage drive information", example="HTS545050A7E380 (465.76 GiB)")
    gpu_model: str = Field(description="GPU model", example="Intel 4th Gen Core Processor Integrated Graphics")
    type: str = Field(description="Device type", example="Laptop")
    user_properties: str = Field(description="Custom user properties", example="(invoice_code:pepe2) (invoice_code2:asd)")
    current_state: str = Field(description="Current device state")
    last_updated: datetime = Field(description="Last update timestamp", example="2025-07-02T21:21:13.626")

class LotInfo(ModelSchema):
    class Meta:
        model = Lot
        fields = ['id', 'name', 'code', 'archived', 'created', 'updated', 'description']

    id: int = Field(..., example=1)
    name: str = Field(..., example="donante-orgA")
    code: Optional[str] = Field(description= "Custom code given by operator", example="INV-001AF")
    archived: bool = Field(..., example=False)
    description:Optional[str] = Field(example="Contains april's inventory")

class LotDevicesResponse(BaseModel):
    lot: LotInfo
    devices: List[DeviceResponse]

class MessageOut(BaseModel):
    error: Optional[str] = Field(None, description="Concise error rmessage.", example="Invalid JSON")
    status: Optional[str] = Field(None, description="More contextual info info", example="Not possible to parse snapshot. Invalid --example-- field")

class DeviceIDInput(BaseModel):
    device_ids: List[str] = Field(
        ...,
        min_length=1,
        description="List of device IDs to assign to the lot",
        example=["0fcdc8469483f9520afae908fc933f618e8913122cb4fdc362a9f3fd6539ff2c"],
        title="Device IDs"
    )

    @validator('device_ids')
    def validate_device_ids(cls, v):
        if not all(isinstance(item, str) and item.strip() for item in v):
            raise ValueError("Device IDs must be non-empty strings")

        return v

class OperationResult(BaseModel):
    success: bool = Field(..., description="Status of operation", example="")
    processed_ids: List[str] = Field(..., description="IDs that were successfully processed")
    invalid_ids: List[str] = Field(default_factory=list, description="IDs that were invalid")
    message: Optional[str] = Field(None, description="Optional warning message")

class PropertyIn(BaseModel):
    value: str = Field(..., min_length=1)

class PropertyOut(ModelSchema):
    class Meta:
        model = UserProperty
        fields = ['key', 'value', 'created']

    device_id: str
    created: datetime = Field(..., alias="created_at")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class SuccessResponse(BaseModel):
    status: str = "success"
    property: PropertyOut
    action: Optional[str] = None

class SnapshotResponse(BaseModel):
    status: str = Field(..., example="success")
    dhid: str = Field(..., description="DeviceHub ID", example="0FCDC8")
    url: str = Field(..., description="Device URL", example="https://example.com/devices/0FCDC8/")
    public_url: str = Field(..., description="Public device URL", example="https://example.com/web/devices/0FCDC8/")
