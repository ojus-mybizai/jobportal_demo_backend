from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from app.models.interview import InterviewStatus
from app.models.job import JobStatus


class JobCandidatesReportItem(BaseModel):
    candidate_id: UUID
    candidate_name: Optional[str] = None
    candidate_email: Optional[str] = None
    candidate_phone: Optional[str] = None
    interviews_count: int
    latest_interview_status: Optional[InterviewStatus] = None
    last_interview_date: Optional[datetime] = None


class CandidateJobsReportItem(BaseModel):
    job_id: UUID
    job_title: Optional[str] = None
    company_id: Optional[UUID] = None
    company_name: Optional[str] = None
    job_status: Optional[JobStatus] = None
    interviews_count: int
    latest_interview_status: Optional[InterviewStatus] = None
    last_interview_date: Optional[datetime] = None
