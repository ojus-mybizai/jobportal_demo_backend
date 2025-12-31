import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, GUID, TimestampMixin


class Company(TimestampMixin, Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("master_company_category.id"), nullable=True, index=True
    )
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_area_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("master_location.id"), nullable=True, index=True
    )
    contact_person: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    alternate_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_map_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    visiting_card_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    front_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    verification_status: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    company_status: Mapped[str] = mapped_column(
        String(10), nullable=False, default="FREE", index=True
    )

    # Relationships
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="company")
    payments: Mapped[list["CompanyPayment"]] = relationship(
        "CompanyPayment",
        back_populates="company",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    category: Mapped[Optional["MasterCompanyCategory"]] = relationship(
        "MasterCompanyCategory"
    )
    location_area: Mapped[Optional["MasterLocation"]] = relationship("MasterLocation")

    @property
    def category_name(self) -> str | None:
        if self.category is None:
            return None
        return self.category.name

    @property
    def location_area_name(self) -> str | None:
        if self.location_area is None:
            return None
        return self.location_area.name


class CompanyPayment(TimestampMixin, Base):
    __tablename__ = "company_payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_company_payments_amount_positive"),
        Index("ix_company_payments_company_id", "company_id"),
        Index("ix_company_payments_payment_date", "payment_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id"), nullable=False
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    company: Mapped["Company"] = relationship("Company", back_populates="payments")
