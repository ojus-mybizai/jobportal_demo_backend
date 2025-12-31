from collections import Counter, defaultdict
from datetime import datetime

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.response import APIResponse, success_response
from app.models.candidate import Candidate, CandidatePayment, CandidateStatus, CourseStructureFee
from app.models.company import Company, CompanyPayment
from app.models.interview import Interview, InterviewStatus
from app.models.job import Job, JobStatus
from app.models.master import MasterLocation
from app.models.placement_income import PlacementIncomePayment
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.report_interviews import CandidateJobsReportItem, JobCandidatesReportItem


router = APIRouter(prefix="/reports", tags=["reports"])


def _fill_status_counts(raw: dict, allowed: list[str]) -> dict[str, int]:
    return {key: int(raw.get(key, 0) or 0) for key in allowed}


def _format_period(value: datetime, group_by: str) -> str:
    if group_by == "day":
        return value.strftime("%Y-%m-%d")
    return value.strftime("%Y-%m")


def _apply_date_range(filters: list, column, start_date: datetime | None, end_date: datetime | None) -> None:
    if start_date is not None:
        filters.append(column >= start_date)
    if end_date is not None:
        filters.append(column <= end_date)


@router.get(
    "/interviews/job-candidates",
    response_model=APIResponse[PaginatedResponse[JobCandidatesReportItem]],
)
async def report_job_candidates(
    job_id: UUID = Query(...),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    status_filter: InterviewStatus | None = Query(None, alias="status"),
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user),
) -> APIResponse[PaginatedResponse[JobCandidatesReportItem]]:
    filters = [Interview.is_active.is_(True), Interview.job_id == job_id]
    _apply_date_range(filters, Interview.interview_date, from_date, to_date)
    if status_filter is not None:
        filters.append(Interview.status == status_filter.value)

    last_date_expr = func.max(Interview.interview_date).label("last_interview_date")

    base_stmt = (
        select(
            Candidate.id.label("candidate_id"),
            Candidate.full_name.label("candidate_name"),
            Candidate.email.label("candidate_email"),
            Candidate.mobile_number.label("candidate_phone"),
            func.count(Interview.id).label("interviews_count"),
            last_date_expr,
        )
        .select_from(Interview)
        .join(Candidate, Candidate.id == Interview.candidate_id)
        .where(*filters)
        .group_by(Candidate.id, Candidate.full_name, Candidate.email, Candidate.mobile_number)
    )

    total_stmt = select(func.count()).select_from(base_stmt.subquery())
    total_res = await session.execute(total_stmt)
    total = int(total_res.scalar_one() or 0)

    stmt = base_stmt.order_by(last_date_expr.desc()).limit(limit).offset((page - 1) * limit)
    res = await session.execute(stmt)
    rows = res.all()

    latest_status_by_candidate: dict[UUID, str] = {}
    if rows:
        candidate_ids = [row.candidate_id for row in rows]
        latest_ts_subq = (
            select(
                Interview.candidate_id.label("candidate_id"),
                func.max(Interview.interview_date).label("max_date"),
            )
            .where(*filters, Interview.candidate_id.in_(candidate_ids))
            .group_by(Interview.candidate_id)
            .subquery()
        )
        latest_status_stmt = (
            select(Interview.candidate_id, Interview.status)
            .join(
                latest_ts_subq,
                (latest_ts_subq.c.candidate_id == Interview.candidate_id)
                & (latest_ts_subq.c.max_date == Interview.interview_date),
            )
            .where(Interview.job_id == job_id, Interview.is_active.is_(True))
        )
        latest_status_res = await session.execute(latest_status_stmt)
        latest_status_by_candidate = {row[0]: row[1] for row in latest_status_res.all()}

    items: list[JobCandidatesReportItem] = []
    for row in rows:
        items.append(
            JobCandidatesReportItem(
                candidate_id=row.candidate_id,
                candidate_name=row.candidate_name,
                candidate_email=row.candidate_email,
                candidate_phone=row.candidate_phone,
                interviews_count=int(row.interviews_count or 0),
                latest_interview_status=latest_status_by_candidate.get(row.candidate_id),
                last_interview_date=row.last_interview_date,
            )
        )

    return success_response(PaginatedResponse[JobCandidatesReportItem](items=items, total=total, page=page, limit=limit))


@router.get(
    "/interviews/candidate-jobs",
    response_model=APIResponse[PaginatedResponse[CandidateJobsReportItem]],
)
async def report_candidate_jobs(
    candidate_id: UUID = Query(...),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    status_filter: InterviewStatus | None = Query(None, alias="status"),
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user),
) -> APIResponse[PaginatedResponse[CandidateJobsReportItem]]:
    filters = [Interview.is_active.is_(True), Interview.candidate_id == candidate_id]
    _apply_date_range(filters, Interview.interview_date, from_date, to_date)
    if status_filter is not None:
        filters.append(Interview.status == status_filter.value)

    last_date_expr = func.max(Interview.interview_date).label("last_interview_date")

    base_stmt = (
        select(
            Job.id.label("job_id"),
            Job.title.label("job_title"),
            Company.id.label("company_id"),
            Company.name.label("company_name"),
            Job.status.label("job_status"),
            func.count(Interview.id).label("interviews_count"),
            last_date_expr,
        )
        .select_from(Interview)
        .join(Job, Job.id == Interview.job_id)
        .join(Company, Company.id == Interview.company_id)
        .where(*filters)
        .group_by(Job.id, Job.title, Company.id, Company.name, Job.status)
    )

    total_stmt = select(func.count()).select_from(base_stmt.subquery())
    total_res = await session.execute(total_stmt)
    total = int(total_res.scalar_one() or 0)

    stmt = base_stmt.order_by(last_date_expr.desc()).limit(limit).offset((page - 1) * limit)
    res = await session.execute(stmt)
    rows = res.all()

    latest_status_by_job: dict[UUID, str] = {}
    if rows:
        job_ids = [row.job_id for row in rows]
        latest_ts_subq = (
            select(
                Interview.job_id.label("job_id"),
                func.max(Interview.interview_date).label("max_date"),
            )
            .where(*filters, Interview.job_id.in_(job_ids))
            .group_by(Interview.job_id)
            .subquery()
        )
        latest_status_stmt = (
            select(Interview.job_id, Interview.status)
            .join(
                latest_ts_subq,
                (latest_ts_subq.c.job_id == Interview.job_id)
                & (latest_ts_subq.c.max_date == Interview.interview_date),
            )
            .where(Interview.candidate_id == candidate_id, Interview.is_active.is_(True))
        )
        latest_status_res = await session.execute(latest_status_stmt)
        latest_status_by_job = {row[0]: row[1] for row in latest_status_res.all()}

    items: list[CandidateJobsReportItem] = []
    for row in rows:
        items.append(
            CandidateJobsReportItem(
                job_id=row.job_id,
                job_title=row.job_title,
                company_id=row.company_id,
                company_name=row.company_name,
                job_status=row.job_status,
                interviews_count=int(row.interviews_count or 0),
                latest_interview_status=latest_status_by_job.get(row.job_id),
                last_interview_date=row.last_interview_date,
            )
        )

    return success_response(PaginatedResponse[CandidateJobsReportItem](items=items, total=total, page=page, limit=limit))


@router.get("/jobs/summary", response_model=APIResponse[dict])
async def jobs_summary(
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin", "recruiter"])),
) -> APIResponse[dict]:
    # Status counts
    job_filters = [Job.is_active.is_(True)]
    _apply_date_range(job_filters, Job.created_at, start_date, end_date)
    status_stmt = (
        select(Job.status, func.count())
        .where(*job_filters)
        .group_by(Job.status)
    )
    status_result = await session.execute(status_stmt)
    status_counts = {row[0]: int(row[1]) for row in status_result.all()}

    # Jobs per company
    jobs_per_company_stmt = (
        select(Company.id, Company.name, func.count(Job.id))
        .join(Job, Job.company_id == Company.id)
        .where(*job_filters)
        .group_by(Company.id, Company.name)
    )
    jobs_per_company_result = await session.execute(jobs_per_company_stmt)
    jobs_per_company = [
        {"company_id": str(row[0]), "company_name": row[1], "count": int(row[2])}
        for row in jobs_per_company_result.all()
    ]

    data = {
        "status_counts": status_counts,
        "jobs_per_company": jobs_per_company,
    }
    return success_response(data)


@router.get("/interviews/summary", response_model=APIResponse[dict])
async def interviews_summary(
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin", "recruiter"])),
) -> APIResponse[dict]:
    interview_filters = [Interview.is_active.is_(True)]
    _apply_date_range(interview_filters, Interview.interview_date, start_date, end_date)
    status_stmt = (
        select(Interview.status, func.count())
        .where(*interview_filters)
        .group_by(Interview.status)
    )
    status_res = await session.execute(status_stmt)
    status_counts = {row[0]: int(row[1]) for row in status_res.all()}

    total_stmt = select(func.count()).select_from(Interview).where(*interview_filters)
    total_res = await session.execute(total_stmt)
    total_interviews = int(total_res.scalar_one() or 0)

    data = {
        "total_interviews": total_interviews,
        "status_counts": status_counts,
    }
    return success_response(data)


@router.get("/placement-incomes/summary", response_model=APIResponse[dict])
async def placement_incomes_summary(
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin", "recruiter"])),
) -> APIResponse[dict]:
    placement_filters = [PlacementIncomePayment.is_active.is_(True)]
    _apply_date_range(placement_filters, PlacementIncomePayment.paid_date, start_date, end_date)
    total_stmt = select(func.coalesce(func.sum(PlacementIncomePayment.amount), 0)).where(*placement_filters)
    total_res = await session.execute(total_stmt)
    total_monthly_amount = int(total_res.scalar_one() or 0)

    count_stmt = select(func.count()).select_from(PlacementIncomePayment).where(*placement_filters)
    count_res = await session.execute(count_stmt)
    total_payments = int(count_res.scalar_one() or 0)

    data = {
        "total_payments": total_payments,
        "total_monthly_amount": total_monthly_amount,
    }
    return success_response(data)


@router.get("/placement-incomes/timeseries", response_model=APIResponse[dict])
async def placement_incomes_timeseries(
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin", "recruiter"])),
) -> APIResponse[dict]:
    month_expr = func.date_trunc("month", PlacementIncomePayment.paid_date)
    placement_filters = [PlacementIncomePayment.is_active.is_(True)]
    _apply_date_range(placement_filters, PlacementIncomePayment.paid_date, start_date, end_date)
    stmt = (
        select(
            month_expr.label("month"),
            func.count().label("count"),
            func.coalesce(func.sum(PlacementIncomePayment.amount), 0).label("amount"),
        )
        .where(*placement_filters)
        .group_by(month_expr)
        .order_by(month_expr)
    )
    res = await session.execute(stmt)

    items = [
        {
            "month": row[0].strftime("%Y-%m"),
            "count": int(row[1]),
            "amount": int(row[2]),
        }
        for row in res.all()
    ]

    return success_response({"items": items})


@router.get("/candidates/summary", response_model=APIResponse[dict])
async def candidates_summary(
    top_n_skills: int = Query(10, ge=1, le=100),
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin", "recruiter"])),
) -> APIResponse[dict]:
    candidate_filters = [Candidate.is_active.is_(True)]
    _apply_date_range(candidate_filters, Candidate.created_at, start_date, end_date)

    # Qualification counts
    qual_counts_stmt = (
        select(Candidate.qualification, func.count())
        .where(*candidate_filters)
        .group_by(Candidate.qualification)
    )
    qual_counts_result = await session.execute(qual_counts_stmt)
    qual_counts_raw = qual_counts_result.all()

    qualification_counts = [
        {
            "qualification": row[0] if row[0] is not None else "Unknown",
            "count": int(row[1]),
        }
        for row in qual_counts_raw
    ]

    # Location counts
    loc_counts_stmt = (
        select(Candidate.location_area_id, func.count())
        .where(*candidate_filters)
        .group_by(Candidate.location_area_id)
    )
    loc_counts_result = await session.execute(loc_counts_stmt)
    loc_counts_raw = loc_counts_result.all()

    loc_names_stmt = select(MasterLocation.id, MasterLocation.name)
    loc_names_result = await session.execute(loc_names_stmt)
    loc_name_map = {row[0]: row[1] for row in loc_names_result.all()}

    location_counts = [
        {
            "location_id": str(row[0]) if row[0] is not None else None,
            "location_name": loc_name_map.get(row[0]) if row[0] is not None else "Unknown",
            "count": int(row[1]),
        }
        for row in loc_counts_raw
    ]

    # Top skills
    skills_stmt = select(Candidate.skills).where(*candidate_filters)
    skills_result = await session.execute(skills_stmt)
    counter: Counter[str] = Counter()

    for (skills,) in skills_result.all():
        if isinstance(skills, list):
            for skill in skills:
                if isinstance(skill, str):
                    key = skill.strip()
                    if key:
                        counter[key] += 1

    top_skills = [
        {"skill": skill, "count": int(count)}
        for skill, count in counter.most_common(top_n_skills)
    ]

    status_stmt = (
        select(Candidate.status, func.count())
        .where(*candidate_filters)
        .group_by(Candidate.status)
    )
    status_result = await session.execute(status_stmt)
    status_breakdown = {row[0]: int(row[1]) for row in status_result.all()}

    fee_filters = [CourseStructureFee.is_active.is_(True)]
    _apply_date_range(fee_filters, CourseStructureFee.created_at, start_date, end_date)
    total_fee_stmt = select(func.coalesce(func.sum(CourseStructureFee.total_fee), 0)).where(*fee_filters)
    total_fee_res = await session.execute(total_fee_stmt)
    total_fee = int(total_fee_res.scalar_one() or 0)

    total_balance_stmt = select(func.coalesce(func.sum(CourseStructureFee.balance), 0)).where(*fee_filters)
    total_balance_res = await session.execute(total_balance_stmt)
    balance_pending = int(total_balance_res.scalar_one() or 0)

    candidate_payment_filters = [CandidatePayment.is_active.is_(True)]
    _apply_date_range(candidate_payment_filters, CandidatePayment.payment_date, start_date, end_date)
    total_paid_stmt = select(func.coalesce(func.sum(CandidatePayment.amount), 0)).where(*candidate_payment_filters)
    total_paid_res = await session.execute(total_paid_stmt)
    total_fees_received = int(total_paid_res.scalar_one() or 0)

    data = {
        "status_breakdown": status_breakdown,
        "qualification_counts": qualification_counts,
        "location_counts": location_counts,
        "top_skills": top_skills,
        "total_fee": total_fee,
        "total_fees_received": total_fees_received,
        "balance_pending": balance_pending,
    }
    return success_response(data)


@router.get("/companies/summary", response_model=APIResponse[dict])
async def companies_summary(
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin", "recruiter"])),
) -> APIResponse[dict]:
    company_filters = [Company.is_active.is_(True)]
    _apply_date_range(company_filters, Company.created_at, start_date, end_date)
    total_companies_stmt = select(func.count()).select_from(Company).where(*company_filters)
    total_companies_res = await session.execute(total_companies_stmt)
    total_companies = int(total_companies_res.scalar_one() or 0)

    paid_free_stmt = (
        select(Company.company_status, func.count())
        .where(*company_filters)
        .group_by(Company.company_status)
    )
    paid_free_res = await session.execute(paid_free_stmt)
    paid_vs_free = {row[0]: int(row[1]) for row in paid_free_res.all()}

    company_payment_filters = []
    _apply_date_range(company_payment_filters, CompanyPayment.payment_date, start_date, end_date)
    total_company_payments_stmt = select(func.coalesce(func.sum(CompanyPayment.amount), 0))
    if company_payment_filters:
        total_company_payments_stmt = total_company_payments_stmt.where(*company_payment_filters)
    total_company_payments_res = await session.execute(total_company_payments_stmt)
    total_payments_received = int(total_company_payments_res.scalar_one() or 0)

    data = {
        "total_companies": total_companies,
        "paid_vs_free": paid_vs_free,
        "total_payments_received": total_payments_received,
    }
    return success_response(data)


@router.get("/dashboard", response_model=APIResponse[dict])
async def dashboard_report(
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin", "recruiter"])),
) -> APIResponse[dict]:
    companies_total_filters = [Company.is_active.is_(True)]
    _apply_date_range(companies_total_filters, Company.created_at, start_date, end_date)
    companies_total_stmt = select(func.count()).select_from(Company).where(*companies_total_filters)
    companies_total_res = await session.execute(companies_total_stmt)
    companies_total = int(companies_total_res.scalar_one() or 0)

    companies_status_stmt = (
        select(Company.company_status, func.count())
        .where(*companies_total_filters)
        .group_by(Company.company_status)
    )
    companies_status_res = await session.execute(companies_status_stmt)
    companies_status = {row[0]: int(row[1]) for row in companies_status_res.all()}

    jobs_filters = [Job.is_active.is_(True)]
    _apply_date_range(jobs_filters, Job.created_at, start_date, end_date)
    jobs_status_stmt = (
        select(Job.status, func.count())
        .where(*jobs_filters)
        .group_by(Job.status)
    )
    jobs_status_res = await session.execute(jobs_status_stmt)
    jobs_status = {row[0]: int(row[1]) for row in jobs_status_res.all()}

    candidates_filters = [Candidate.is_active.is_(True)]
    _apply_date_range(candidates_filters, Candidate.created_at, start_date, end_date)
    candidates_status_stmt = (
        select(Candidate.status, func.count())
        .where(*candidates_filters)
        .group_by(Candidate.status)
    )
    candidates_status_res = await session.execute(candidates_status_stmt)
    candidates_status = {row[0]: int(row[1]) for row in candidates_status_res.all()}

    interviews_filters = [Interview.is_active.is_(True)]
    _apply_date_range(interviews_filters, Interview.interview_date, start_date, end_date)
    interviews_status_stmt = (
        select(Interview.status, func.count())
        .where(*interviews_filters)
        .group_by(Interview.status)
    )
    interviews_status_res = await session.execute(interviews_status_stmt)
    interviews_status = {row[0]: int(row[1]) for row in interviews_status_res.all()}

    company_payment_filters = []
    _apply_date_range(company_payment_filters, CompanyPayment.payment_date, start_date, end_date)
    company_payments_stmt = select(func.coalesce(func.sum(CompanyPayment.amount), 0))
    if company_payment_filters:
        company_payments_stmt = company_payments_stmt.where(*company_payment_filters)
    company_payments_res = await session.execute(company_payments_stmt)
    company_payments_total = int(company_payments_res.scalar_one() or 0)

    candidate_payment_filters = [CandidatePayment.is_active.is_(True)]
    _apply_date_range(candidate_payment_filters, CandidatePayment.payment_date, start_date, end_date)
    candidate_payments_stmt = select(func.coalesce(func.sum(CandidatePayment.amount), 0)).where(*candidate_payment_filters)
    candidate_payments_res = await session.execute(candidate_payments_stmt)
    candidate_payments_total = int(candidate_payments_res.scalar_one() or 0)

    placement_filters = [PlacementIncomePayment.is_active.is_(True)]
    _apply_date_range(placement_filters, PlacementIncomePayment.paid_date, start_date, end_date)
    placement_income_stmt = select(func.coalesce(func.sum(PlacementIncomePayment.amount), 0)).where(*placement_filters)
    placement_income_res = await session.execute(placement_income_stmt)
    placement_income_total = int(placement_income_res.scalar_one() or 0)

    total_income = company_payments_total + candidate_payments_total + placement_income_total

    data = {
        "companies": {
            "total": companies_total,
            "paid": int(companies_status.get("PAID", 0) or 0),
            "free": int(companies_status.get("FREE", 0) or 0),
        },
        "jobs": _fill_status_counts(jobs_status, [x.value for x in JobStatus]),
        "candidates": _fill_status_counts(candidates_status, [x.value for x in CandidateStatus]),
        "interviews": _fill_status_counts(interviews_status, [x.value for x in InterviewStatus]),
        "finance": {
            "company_payments": company_payments_total,
            "candidate_fees_received": candidate_payments_total,
            "placement_income": placement_income_total,
            "total_income": total_income,
        },
    }
    return success_response(data)


@router.get("/finance/summary", response_model=APIResponse[dict])
async def finance_summary(
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin", "recruiter"])),
) -> APIResponse[dict]:
    company_filters = []
    candidate_filters = [CandidatePayment.is_active.is_(True)]
    placement_filters = [PlacementIncomePayment.is_active.is_(True)]

    if start_date is not None:
        company_filters.append(CompanyPayment.payment_date >= start_date)
        candidate_filters.append(CandidatePayment.payment_date >= start_date)
        placement_filters.append(PlacementIncomePayment.paid_date >= start_date)
    if end_date is not None:
        company_filters.append(CompanyPayment.payment_date <= end_date)
        candidate_filters.append(CandidatePayment.payment_date <= end_date)
        placement_filters.append(PlacementIncomePayment.paid_date <= end_date)

    company_stmt = select(func.coalesce(func.sum(CompanyPayment.amount), 0))
    if company_filters:
        company_stmt = company_stmt.where(*company_filters)
    company_res = await session.execute(company_stmt)
    company_total = int(company_res.scalar_one() or 0)

    candidate_stmt = select(func.coalesce(func.sum(CandidatePayment.amount), 0))
    if candidate_filters:
        candidate_stmt = candidate_stmt.where(*candidate_filters)
    candidate_res = await session.execute(candidate_stmt)
    candidate_total = int(candidate_res.scalar_one() or 0)

    placement_stmt = select(func.coalesce(func.sum(PlacementIncomePayment.amount), 0)).where(*placement_filters)
    placement_res = await session.execute(placement_stmt)
    placement_total = int(placement_res.scalar_one() or 0)

    total_income = company_total + candidate_total + placement_total
    return success_response(
        {
            "company_payments": company_total,
            "candidate_payments": candidate_total,
            "placement_income": placement_total,
            "total_income": total_income,
        }
    )


@router.get("/finance/breakdown", response_model=APIResponse[dict])
async def finance_breakdown(
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    group_by: str = Query("month"),
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin", "recruiter"])),
) -> APIResponse[dict]:
    if group_by not in {"day", "month"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="group_by must be either 'day' or 'month'",
        )
    company_filters = []
    candidate_filters = [CandidatePayment.is_active.is_(True)]
    placement_filters = [PlacementIncomePayment.is_active.is_(True)]

    if start_date is not None:
        company_filters.append(CompanyPayment.payment_date >= start_date)
        candidate_filters.append(CandidatePayment.payment_date >= start_date)
        placement_filters.append(PlacementIncomePayment.paid_date >= start_date)
    if end_date is not None:
        company_filters.append(CompanyPayment.payment_date <= end_date)
        candidate_filters.append(CandidatePayment.payment_date <= end_date)
        placement_filters.append(PlacementIncomePayment.paid_date <= end_date)

    company_period = func.date_trunc(group_by, CompanyPayment.payment_date)
    company_stmt = select(company_period, func.coalesce(func.sum(CompanyPayment.amount), 0)).group_by(company_period)
    if company_filters:
        company_stmt = company_stmt.where(*company_filters)
    company_res = await session.execute(company_stmt)

    candidate_period = func.date_trunc(group_by, CandidatePayment.payment_date)
    candidate_stmt = (
        select(candidate_period, func.coalesce(func.sum(CandidatePayment.amount), 0))
        .group_by(candidate_period)
    )
    if candidate_filters:
        candidate_stmt = candidate_stmt.where(*candidate_filters)
    candidate_res = await session.execute(candidate_stmt)

    placement_period = func.date_trunc(group_by, PlacementIncomePayment.paid_date)
    placement_stmt = (
        select(placement_period, func.coalesce(func.sum(PlacementIncomePayment.amount), 0))
        .where(*placement_filters)
        .group_by(placement_period)
    )
    placement_res = await session.execute(placement_stmt)

    merged: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "company_payments": 0,
            "candidate_payments": 0,
            "placement_income": 0,
        }
    )

    for period_dt, amount in company_res.all():
        if period_dt is None:
            continue
        merged[_format_period(period_dt, group_by)]["company_payments"] = int(amount or 0)
    for period_dt, amount in candidate_res.all():
        if period_dt is None:
            continue
        merged[_format_period(period_dt, group_by)]["candidate_payments"] = int(amount or 0)
    for period_dt, amount in placement_res.all():
        if period_dt is None:
            continue
        merged[_format_period(period_dt, group_by)]["placement_income"] = int(amount or 0)

    items = []
    for period in sorted(merged.keys()):
        row = merged[period]
        total = int(row["company_payments"] + row["candidate_payments"] + row["placement_income"])
        items.append(
            {
                "period": period,
                "company_payments": int(row["company_payments"]),
                "candidate_payments": int(row["candidate_payments"]),
                "placement_income": int(row["placement_income"]),
                "total": total,
            }
        )

    return success_response({"items": items})
