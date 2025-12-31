import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, GUID, TimestampMixin


class PlacementIncome(TimestampMixin, Base):
    __tablename__ = "placement_incomes"
    __table_args__ = (
        CheckConstraint(
            "total_receivable > 0",
            name="ck_placement_incomes_total_receivable_positive",
        ),
        Index("ix_placement_incomes_interview_id", "interview_id"),
        Index("ix_placement_incomes_candidate_id", "candidate_id"),
        Index("ix_placement_incomes_job_id", "job_id"),
        Index("ix_placement_incomes_due_date", "due_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    interview_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("interviews.id"), nullable=False
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("candidates.id"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("jobs.id"), nullable=False)

    total_receivable: Mapped[int] = mapped_column(Integer, nullable=False)
    total_received: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    interview: Mapped["Interview"] = relationship("Interview")
    candidate: Mapped["Candidate"] = relationship("Candidate")
    job: Mapped["Job"] = relationship("Job")

    payments: Mapped[list["PlacementIncomePayment"]] = relationship(
        "PlacementIncomePayment",
        back_populates="placement_income",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class PlacementIncomePayment(TimestampMixin, Base):
    __tablename__ = "placement_income_payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_placement_income_payments_amount_positive"),
        Index("ix_placement_income_payments_income_id", "placement_income_id"),
        Index("ix_placement_income_payments_paid_date", "paid_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    placement_income_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("placement_incomes.id"), nullable=False
    )

    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    paid_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    placement_income: Mapped[PlacementIncome] = relationship(
        "PlacementIncome",
        back_populates="payments",
    )
