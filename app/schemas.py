from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UserBase(BaseModel):
    username: str
    full_name: Optional[str] = None


class UserCreate(UserBase):
    pass


class UserRead(UserBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class SampleTypeBase(BaseModel):
    name: str
    description: Optional[str] = None


class SampleTypeCreate(SampleTypeBase):
    pass


class SampleTypeRead(SampleTypeBase):
    id: int

    class Config:
        from_attributes = True


class SampleBase(BaseModel):
    sample_id: str
    name: Optional[str] = None
    status: str = "active"
    volume: Optional[float] = None
    volume_units: Optional[str] = None
    sample_type_id: Optional[int] = None
    notes: Optional[str] = None


class SampleCreate(SampleBase):
    pass


class SampleUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    volume: Optional[float] = None
    volume_units: Optional[str] = None
    sample_type_id: Optional[int] = None
    notes: Optional[str] = None


class SampleRead(SampleBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class StorageNodeBase(BaseModel):
    name: str
    node_type: str
    parent_id: Optional[int] = None


class StorageNodeCreate(StorageNodeBase):
    pass


class StorageNodeRead(StorageNodeBase):
    id: int

    class Config:
        from_attributes = True


class StoragePositionRead(BaseModel):
    id: int
    box_id: int
    row: int
    col: int
    label: str

    class Config:
        from_attributes = True


class PlaceSampleRequest(BaseModel):
    position_id: int = Field(..., description="Storage position id")


class MoveSampleRequest(BaseModel):
    to_position_id: int


class EventRead(BaseModel):
    id: int
    event_type: str
    user_id: Optional[int] = None
    sample_id: Optional[int] = None
    from_position_id: Optional[int] = None
    to_position_id: Optional[int] = None
    payload_json: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
