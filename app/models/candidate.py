import uuid

import enum
from datetime import datetime, date

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, GUID, TimestampMixin
from app.models.master import MasterLocation, ExperienceLevel


class CandidateStatus(str, enum.Enum):
    REGISTERED = "REGISTERED"
    COURSE = "COURSE"
    FREE = "FREE"


class CandidateEmploymentStatus(str, enum.Enum):
    EMPLOYED = "EMPLOYED"
    UNEMPLOYED = "UNEMPLOYED"


class Gender(str, enum.Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"
    BOTH = "BOTH"



class Candidate(TimestampMixin, Base):
    __tablename__ = "candidates"
    __table_args__ = (
        UniqueConstraint("email", name="uq_candidates_email"),
        UniqueConstraint("mobile_number", name="uq_candidates_mobile_number"),
        Index("ix_candidates_location_area_id", "location_area_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mobile_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    qualification: Mapped[str | None] = mapped_column(Text, nullable=True)
    experience_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    resume_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_salary: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dob: Mapped[date | None] = mapped_column(Date, nullable=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    location_area_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("master_location.id"), nullable=True
    )
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_preferences: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=CandidateStatus.REGISTERED.value, index=True
    )
    skills: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    education: Mapped[list | None] = mapped_column(JSON, nullable=True)
    degree: Mapped[list | None] = mapped_column(JSON, nullable=True)

    employment_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=CandidateEmploymentStatus.UNEMPLOYED.value,
        index=True,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    fee_structure: Mapped["CourseStructureFee"] = relationship(
        "CourseStructureFee",
        back_populates="candidate",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    payments: Mapped[list["CandidatePayment"]] = relationship(
        "CandidatePayment",
        back_populates="candidate",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    location_area: Mapped[MasterLocation | None] = relationship("MasterLocation")

    @property
    def location_area_name(self) -> str | None:
        if self.location_area is None:
            return None
        return self.location_area.name

class CourseStructureFee(TimestampMixin, Base):
    __tablename__ = "course_structure_fees"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("candidates.id"), nullable=False, index=True
    )
    total_fee: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="fee_structure")


class CandidatePayment(TimestampMixin, Base):
    __tablename__ = "candidate_payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_candidate_payments_amount_positive"),
        Index("ix_candidate_payments_candidate_id", "candidate_id"),
        Index("ix_candidate_payments_payment_date", "payment_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("candidates.id"), nullable=False
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="payments")
