from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import AnyUrl, BaseModel, EmailStr, Field, constr, field_validator


class CompanyPaymentBase(BaseModel):
    amount: int = Field(..., gt=0)
    payment_date: datetime
    remarks: Optional[str] = None


class CompanyPaymentCreate(CompanyPaymentBase):
    pass


class CompanyPaymentRead(CompanyPaymentBase):
    id: UUID

    class Config:
        from_attributes = True


class CompanyPublicRead(BaseModel):
    id: UUID
    name: str
    address: Optional[str] = None
    category_name: Optional[str] = None
    location_area_name: Optional[str] = None
    contact_person: Optional[str] = None
    contact_number: Optional[str] = None
    alternate_number: Optional[str] = None
    email: Optional[EmailStr] = None
    google_map_url: Optional[AnyUrl] = None
    location_link: Optional[str] = None
    visiting_card_url: Optional[str] = None
    front_image_url: Optional[str] = None
    notes: Optional[str] = None

    class Config:
        from_attributes = True


class CompanyBase(BaseModel):
    name: constr(min_length=1)
    category_id: Optional[UUID] = None
    address: Optional[str] = None
    location_area_id: Optional[UUID] = None
    contact_person: Optional[str] = None
    contact_number: Optional[str] = None
    alternate_number: Optional[str] = None
    email: Optional[EmailStr] = None
    google_map_url: Optional[AnyUrl] = None
    location_link: Optional[str] = None
    notes: Optional[str] = None


class CompanyCreate(CompanyBase):
    verification_status: bool = False
    company_status: str = "FREE"  # FREE or PAID
    payments: Optional[List[CompanyPaymentCreate]] = Field(default_factory=list)

    @field_validator("company_status")
    @classmethod
    def validate_company_status(cls, v: str) -> str:  # type: ignore[override]
        if v not in {"FREE", "PAID"}:
            raise ValueError("company_status must be either 'FREE' or 'PAID'")
        return v


class CompanyUpdate(BaseModel):
    name: Optional[constr(min_length=1)] = None
    category_id: Optional[UUID] = None
    address: Optional[str] = None
    location_area_id: Optional[UUID] = None
    contact_person: Optional[str] = None
    contact_number: Optional[str] = None
    alternate_number: Optional[str] = None
    email: Optional[EmailStr] = None
    google_map_url: Optional[AnyUrl] = None
    location_link: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None
    verification_status: Optional[bool] = None
    company_status: Optional[str] = None
    payments: Optional[List[CompanyPaymentCreate]] = None

    @field_validator("company_status")
    @classmethod
    def validate_company_status(cls, v: Optional[str]) -> Optional[str]:  # type: ignore[override]
        if v is not None and v not in {"FREE", "PAID"}:
            raise ValueError("company_status must be either 'FREE' or 'PAID'")
        return v


class CompanyRead(CompanyBase):
    id: UUID
    category_name: Optional[str] = None
    location_area_name: Optional[str] = None
    contact_person: Optional[str] = None
    contact_number: Optional[str] = None
    alternate_number: Optional[str] = None
    email: Optional[EmailStr] = None
    google_map_url: Optional[AnyUrl] = None
    location_link: Optional[str] = None
    visiting_card_url: Optional[str] = None
    front_image_url: Optional[str] = None
    notes: Optional[str] = None
    verification_status: bool
    company_status: str
    payments: List[CompanyPaymentRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    is_active: bool

    class Config:
        from_attributes = True
