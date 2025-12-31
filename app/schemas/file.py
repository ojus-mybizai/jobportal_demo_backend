from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class FileRead(BaseModel):
    id: UUID
    url: str
    filename: str
    mimetype: Optional[str] = None
    size: Optional[int] = None
    uploaded_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
