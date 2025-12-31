from datetime import datetime, date
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, computed_field, field_validator, model_validator

from app.models.candidate import CandidateEmploymentStatus, CandidateStatus, Gender
from app.models.master import ExperienceLevel
from app.schemas.candidate_payment import CandidatePaymentCreate, CandidatePaymentRead


class CandidateBase(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    mobile_number: Optional[str] = None
    qualification: Optional[str] = None
    experience_level: Optional[ExperienceLevel] = None
    skills: Optional[list[str] | dict] = None  # list of MasterSkill ids
    expected_salary: Optional[int] = Field(default=None, ge=0)
    location_area_id: Optional[UUID] = None
    address: Optional[str] = None
    job_preferences: Optional[dict | list] = None
    notes: Optional[str] = None
    reference: Optional[str] = None
    status: CandidateStatus = CandidateStatus.REGISTERED
    education: Optional[List[str]] = None  # list of MasterEducation ids
    degree: Optional[List[str]] = None  # list of MasterDegree ids
    gender: Optional[Gender] = None
    dob: Optional[date] = None

    @field_validator("mobile_number")
    @classmethod
    def validate_mobile(cls, v):  # type: ignore[override]
        if v and len(v) < 7:
            raise ValueError("mobile_number appears invalid")
        return v


class CandidateCreate(CandidateBase):
    fee_structure: Optional["CourseStructureFeeCreate"] = None
    initial_payment: Optional[CandidatePaymentCreate] = None

    @model_validator(mode="after")
    def _validate_flow(self):
        if self.status in {CandidateStatus.FREE}:
            if self.fee_structure is not None or self.initial_payment is not None:
                raise ValueError("fee_structure and initial_payment are not allowed for FREE")
        if self.status == CandidateStatus.REGISTERED:
            if self.initial_payment is None:
                raise ValueError("initial_payment is required when status is REGISTERED")
            if self.fee_structure is not None:
                raise ValueError("fee_structure is not allowed when status is REGISTERED")
        if self.status == CandidateStatus.COURSE:
            if self.fee_structure is None:
                raise ValueError("fee_structure is required when status is COURSE")
            if self.initial_payment is None:
                raise ValueError("initial_payment is required when status is COURSE")
        return self


class CandidateUpdate(CandidateBase):
    is_active: Optional[bool] = None
    fee_structure: Optional["CourseStructureFeeCreate"] = None
    initial_payment: Optional[CandidatePaymentCreate] = None
    age: Optional[int] = None  # ignored if dob provided


class CandidateStatusChange(BaseModel):
    status: CandidateStatus
    fee_structure: Optional["CourseStructureFeeCreate"] = None
    initial_payment: Optional[CandidatePaymentCreate] = None


class CourseStructureFeeBase(BaseModel):
    total_fee: int = Field(default=0, ge=0)
    due_date: Optional[datetime] = None


class CourseStructureFeeCreate(CourseStructureFeeBase):
    pass


class CourseStructureFeeRead(CourseStructureFeeBase):
    id: UUID
    candidate_id: UUID
    balance: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


CandidateCreate.model_rebuild()
CandidateUpdate.model_rebuild()


class CandidateRead(CandidateBase):
    id: UUID
    resume_url: Optional[str] = None
    photo_url: Optional[str] = None
    location_area_name: Optional[str] = None
    skills_names: Optional[List[str]] = None
    education_names: Optional[List[str]] = None
    degree_names: Optional[List[str]] = None
    employment_status: CandidateEmploymentStatus = CandidateEmploymentStatus.UNEMPLOYED
    interviews_count: Optional[int] = None
    fee_structure: Optional[CourseStructureFeeRead] = None
    payments: Optional[List[CandidatePaymentRead]] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    age: Optional[int] = None

    @computed_field(return_type=Optional[int])
    @property
    def total_fee(self) -> Optional[int]:
        if self.fee_structure is None:
            return None
        return int(self.fee_structure.total_fee)

    @computed_field(return_type=Optional[int])
    @property
    def balance(self) -> Optional[int]:
        if self.fee_structure is None:
            return None
        return int(self.fee_structure.balance)

    class Config:
        from_attributes = True
