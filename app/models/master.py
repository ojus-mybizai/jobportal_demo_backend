import uuid

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, GUID, TimestampMixin


class MasterMixin(TimestampMixin):
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    


class MasterCompanyCategory(MasterMixin, Base):
    __tablename__ = "master_company_category"


class MasterLocation(MasterMixin, Base):
    __tablename__ = "master_location"


class MasterJobCategory(MasterMixin, Base):
    __tablename__ = "master_job_category"


class MasterExperienceLevel(MasterMixin, Base):
    __tablename__ = "master_experience_level"


class MasterSkill(MasterMixin, Base):
    __tablename__ = "master_skill"


class MasterEducation(MasterMixin, Base):
    __tablename__ = "master_education"


class MasterDegree(MasterMixin, Base):
    __tablename__ = "master_degree"
