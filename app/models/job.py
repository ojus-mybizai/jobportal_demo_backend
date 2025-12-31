import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, GUID, TimestampMixin
from app.models.master import MasterJobCategory, MasterLocation, ExperienceLevel


class JobStatus(str, enum.Enum):
    OPEN = "OPEN"
    FULFILLED = "FULFILLED"
    DROPPED = "DROPPED"

class JobType(str, enum.Enum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    INTERNSHIP = "INTERNSHIP"

class Gender(str, enum.Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"
    BOTH = "BOTH"


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("num_vacancies >= 0", name="ck_jobs_num_vacancies_positive"),
        CheckConstraint(
            "salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max",
            name="ck_jobs_salary_bounds",
        ),
        Index("ix_jobs_company_id", "company_id"),
        Index("ix_jobs_title", "title"),
        Index("ix_jobs_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    num_vacancies: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    job_categories: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)  # list of MasterJobCategory ids

    job_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default=JobType.FULL_TIME.value
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    responsibilities: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_area_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("master_location.id"), nullable=True
    )
    skills: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)  # list of MasterSkill ids
    education: Mapped[list | None] = mapped_column(JSON, nullable=True)  # list of MasterEducation ids
    degree: Mapped[list | None] = mapped_column(JSON, nullable=True)  # list of MasterDegree ids
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    experience_level: Mapped[str | None] = mapped_column(String(20), nullable=True)

    contact_person: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=JobStatus.OPEN.value
    )

    attachments: Mapped[list | None] = mapped_column(JSON, nullable=True)
    joined_candidates: Mapped[list["Joined_candidates"]] = relationship("Joined_candidates", back_populates="job")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    company: Mapped["Company"] = relationship("Company", back_populates="jobs")
    location_area: Mapped[MasterLocation | None] = relationship("MasterLocation")


    @property
    def company_name(self) -> str | None:
        if self.company is None:
            return None
        return self.company.name

    @property
    def location_area_name(self) -> str | None:
        if self.location_area is None:
            return None
        return self.location_area.name


class Joined_candidates(TimestampMixin, Base):
    __tablename__ = "joined_candidates"
    __table_args__ = (
        Index("ix_joined_candidates_job_id", "job_id"),
        Index("ix_joined_candidates_candidate_id", "candidate_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("jobs.id"), nullable=False)
    candidate_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("candidates.id"), nullable=False)
    Date_of_joining: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    salary: Mapped[int] = mapped_column(Integer, nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    job: Mapped["Job"] = relationship("Job", back_populates="joined_candidates")
    candidate: Mapped["Candidate"] = relationship("Candidate")

    @property
    def candidate_name(self) -> str | None:
        if self.candidate is None:
            return None
        return self.candidate.full_name