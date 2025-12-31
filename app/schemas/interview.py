from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.interview import InterviewStatus


class InterviewBase(BaseModel):
    company_id: UUID
    job_id: UUID
    candidate_id: UUID
    interview_date: datetime
    status: InterviewStatus = InterviewStatus.SCHEDULED
    remarks: Optional[str] = None


class InterviewCreate(InterviewBase):
    pass


class InterviewUpdate(BaseModel):
    company_id: Optional[UUID] = None
    job_id: Optional[UUID] = None
    candidate_id: Optional[UUID] = None
    interview_date: Optional[datetime] = None
    status: Optional[InterviewStatus] = None
    remarks: Optional[str] = None
    is_active: Optional[bool] = None


class InterviewStatusUpdate(BaseModel):
    status: InterviewStatus
    doj: Optional[datetime] = None
    salary: Optional[int] = Field(default=None, gt=0)
    placement_total_receivable: Optional[int] = Field(default=None, gt=0)
    placement_due_date: Optional[datetime] = None
    placement_remarks: Optional[str] = None


class InterviewRead(InterviewBase):
    id: UUID
    placement_income_id: Optional[UUID] = None
    company_name: Optional[str] = None
    job_title: Optional[str] = None
    candidate_name: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
