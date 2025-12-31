from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, constr


class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    role: Literal["admin", "recruiter", "viewer"] = "viewer"
    is_active: bool = True


class UserCreate(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    password: constr(min_length=8)
    role: Literal["admin", "recruiter", "viewer"] = "recruiter"


class UserRead(UserBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
