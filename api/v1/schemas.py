# api/v1/schemas.py
from pydantic import BaseModel

from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

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
