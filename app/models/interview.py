import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, GUID, TimestampMixin


class InterviewStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    REJECTED_BY_EMPLOYER = "REJECTED_BY_EMPLOYER"
    REJECTED_BY_CANDIDATE = "REJECTED_BY_CANDIDATE"
    ON_HOLD = "ON_HOLD"
    JOINED = "JOINED"


class Interview(TimestampMixin, Base):
    __tablename__ = "interviews"
    __table_args__ = (
        Index("ix_interviews_company_id", "company_id"),
        Index("ix_interviews_job_id", "job_id"),
        Index("ix_interviews_candidate_id", "candidate_id"),
        Index("ix_interviews_status", "status"),
        Index("ix_interviews_interview_date", "interview_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("jobs.id"), nullable=False)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("candidates.id"), nullable=False
    )
    interview_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=InterviewStatus.SCHEDULED.value
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    company: Mapped["Company"] = relationship("Company")
    job: Mapped["Job"] = relationship("Job")
    candidate: Mapped["Candidate"] = relationship("Candidate")
