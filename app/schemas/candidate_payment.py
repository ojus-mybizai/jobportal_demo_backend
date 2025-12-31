from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CandidatePaymentBase(BaseModel):
    amount: int = Field(..., gt=0)
    payment_date: datetime
    remarks: Optional[str] = None


class CandidatePaymentCreate(CandidatePaymentBase):
    pass


class CandidatePaymentRead(CandidatePaymentBase):
    id: UUID
    candidate_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
