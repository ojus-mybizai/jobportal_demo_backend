from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.placement_income_payment import PlacementIncomePaymentRead


class PlacementIncomeBase(BaseModel):
    interview_id: UUID
    candidate_id: UUID
    job_id: UUID
    total_receivable: int = Field(..., gt=0)
    due_date: datetime
    remarks: Optional[str] = None


class PlacementIncomeCreate(PlacementIncomeBase):
    pass


class PlacementIncomeUpdate(BaseModel):
    total_receivable: Optional[int] = Field(default=None, gt=0)
    due_date: Optional[datetime] = None
    remarks: Optional[str] = None
    is_active: Optional[bool] = None


class PlacementIncomeRead(PlacementIncomeBase):
    id: UUID
    total_received: int
    balance: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    payments: list[PlacementIncomePaymentRead] = []

    class Config:
        from_attributes = True
