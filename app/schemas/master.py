from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, constr


class MasterBase(BaseModel):
    name: constr(min_length=1)



class MasterCreate(MasterBase):
    pass


class MasterUpdate(BaseModel):
    name: Optional[constr(min_length=1)] = None


class MasterRead(MasterBase):
    id: UUID
    name: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
