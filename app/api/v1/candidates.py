from typing import List, Optional
from uuid import UUID
from datetime import date, datetime

from fastapi import APIRouter, Depends, File as FastAPIFile, HTTPException, Query, UploadFile, status
from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.api import deps
from app.core.response import APIResponse, success_response
from app.models.candidate import (
    Candidate,
    CandidateEmploymentStatus,
    CandidatePayment,
    CandidateStatus,
    ExperienceLevel,
    Gender,
    CourseStructureFee,
)
from app.models.interview import Interview
from app.models.job import Job, JobStatus
from app.models.company import Company
from app.models.user import User
from app.models.master import MasterSkill, MasterEducation, MasterDegree, MasterLocation
from app.schemas.candidate import CandidateCreate, CandidateRead, CandidateUpdate, CandidateStatusChange
from app.schemas.common import PaginatedResponse
from app.schemas.report_interviews import CandidateJobsReportItem
from app.schemas.job import RelatedJobItem
from app.services.file_service import FileService


router = APIRouter(prefix="/candidates", tags=["candidates"])


async def _master_names_by_ids(
    session: AsyncSession,
    model,
    ids: Optional[list[str] | list],
) -> list[str]:
    if not ids:
        return []
    try:
        id_list = list({UUID(str(i)) for i in ids})
    except Exception:
        return []
    stmt = select(model.name).where(model.id.in_(id_list))
    res = await session.execute(stmt)
    return [r[0] for r in res.all() if r[0] is not None]


async def _validate_master_ids(session: AsyncSession, model, ids: Optional[list[str] | list]) -> None:
    if not ids:
        return
    # Normalize to list of unique IDs
    try:
        id_list = list({UUID(str(i)) for i in ids})
    except Exception:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid ID format in list")

    stmt = select(func.count()).select_from(model).where(model.id.in_(id_list))
    res = await session.execute(stmt)
    found = int(res.scalar_one() or 0)
    if found != len(id_list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"One or more {model.__tablename__} ids are invalid",
        )


def _as_uuid_list(value: Optional[list | dict]) -> list[UUID]:
    if not value:
        return []
    if isinstance(value, dict):
        value = list(value.values())
    result: list[UUID] = []
    for v in value:
        try:
            result.append(UUID(str(v)))
        except Exception:
            continue
    return result


async def _hydrate_candidate_with_names(session: AsyncSession, candidate: Candidate) -> CandidateRead:
    skills_names = await _master_names_by_ids(session, MasterSkill, candidate.skills)
    education_names = await _master_names_by_ids(session, MasterEducation, candidate.education)
    degree_names = await _master_names_by_ids(session, MasterDegree, candidate.degree)
    payload = CandidateRead.model_validate(candidate)
    payload.skills_names = skills_names
    payload.education_names = education_names
    payload.degree_names = degree_names
    return payload


@router.get("/", response_model=APIResponse[PaginatedResponse[CandidateRead]])
async def list_candidates(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    q: Optional[str] = Query(None, description="Search in name, email, mobile"),
    email: Optional[str] = Query(None),
    mobile_number: Optional[str] = Query(None),
    status_filter: Optional[CandidateStatus] = Query(None, alias="status"),
    employment_status: Optional[CandidateEmploymentStatus] = Query(None),
    qualification: Optional[str] = Query(None),
    location_area_id: Optional[UUID] = Query(None),
    expected_salary_min: Optional[int] = Query(None, ge=0),
    expected_salary_max: Optional[int] = Query(None, ge=0),
    experience_level: Optional["ExperienceLevel"] = Query(None),
    skills: Optional[List[str]] = Query(None),
    gender: Optional[Gender] = Query(None),
    has_resume: Optional[bool] = Query(None),
    has_photo: Optional[bool] = Query(None),
    created_from: Optional[datetime] = Query(None),
    created_to: Optional[datetime] = Query(None),
    is_active: Optional[bool] = Query(True),
    sort_by: str = Query("created_at"),
    order: str = Query("desc"),
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user),
) -> APIResponse[PaginatedResponse[CandidateRead]]:
    stmt = select(Candidate).options(
        joinedload(Candidate.location_area),
        selectinload(Candidate.fee_structure),
        selectinload(Candidate.payments),
    )
    filters = []

    if is_active is not None:
        filters.append(Candidate.is_active.is_(is_active))
    if status_filter is not None:
        filters.append(Candidate.status == status_filter.value)
    if employment_status is not None:
        filters.append(Candidate.employment_status == employment_status.value)
    if qualification:
        filters.append(Candidate.qualification.ilike(f"%{qualification}%"))
    if location_area_id:
        filters.append(Candidate.location_area_id == location_area_id)
    if expected_salary_min is not None:
        filters.append(Candidate.expected_salary >= expected_salary_min)
    if expected_salary_max is not None:
        filters.append(Candidate.expected_salary <= expected_salary_max)
    if experience_level is not None:
        filters.append(Candidate.experience_level == experience_level.value)
    if gender is not None:
        filters.append(Candidate.gender == gender.value)
    if skills:
        filters.append(Candidate.skills.contains(skills))
    if has_resume is True:
        filters.append(Candidate.resume_url.is_not(None))
    if has_resume is False:
        filters.append(Candidate.resume_url.is_(None))
    if has_photo is True:
        filters.append(Candidate.photo_url.is_not(None))
    if has_photo is False:
        filters.append(Candidate.photo_url.is_(None))
    if created_from is not None:
        filters.append(Candidate.created_at >= created_from)
    if created_to is not None:
        filters.append(Candidate.created_at <= created_to)
    if q:
        like = f"%{q}%"
        filters.append(
            or_(
                Candidate.full_name.ilike(like),
                Candidate.email.ilike(like),
                Candidate.mobile_number.ilike(like),
            )
        )
    if email:
        filters.append(Candidate.email.ilike(email.strip()))
    if mobile_number:
        filters.append(Candidate.mobile_number.ilike(mobile_number.strip()))

    if filters:
        stmt = stmt.where(and_(*filters))

    allowed_sort_fields = {
        "created_at": Candidate.created_at,
        "updated_at": Candidate.updated_at,
        "full_name": Candidate.full_name,
        "expected_salary": Candidate.expected_salary,
        "experience_level": Candidate.experience_level,
        "status": Candidate.status,
        "employment_status": Candidate.employment_status,
    }
    if sort_by not in allowed_sort_fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid sort_by. Allowed: {', '.join(sorted(allowed_sort_fields.keys()))}",
        )
    normalized_order = (order or "desc").strip().lower()
    if normalized_order not in {"asc", "desc"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="order must be either 'asc' or 'desc'",
        )
    sort_attr = allowed_sort_fields[sort_by]
    stmt = stmt.order_by(sort_attr.asc() if normalized_order == "asc" else sort_attr.desc())
    stmt = stmt.limit(limit).offset((page - 1) * limit)

    total_stmt = select(func.count()).select_from(Candidate)
    if filters:
        total_stmt = total_stmt.where(and_(*filters))

    result = await session.execute(stmt)
    candidates = result.scalars().all()
    candidate_ids = [c.id for c in candidates]
    counts_by_candidate: dict[UUID, int] = {}
    if candidate_ids:
        counts_stmt = (
            select(Interview.candidate_id, func.count())
            .where(and_(Interview.is_active.is_(True), Interview.candidate_id.in_(candidate_ids)))
            .group_by(Interview.candidate_id)
        )
        counts_res = await session.execute(counts_stmt)
        counts_by_candidate = {row[0]: int(row[1] or 0) for row in counts_res.all()}

    items = []
    for obj in candidates:
        if getattr(obj, "employment_status", None) is None:
            obj.employment_status = CandidateEmploymentStatus.UNEMPLOYED.value
        payload = await _hydrate_candidate_with_names(session, obj)
        payload.interviews_count = counts_by_candidate.get(obj.id, 0)
        items.append(payload)

    total_result = await session.execute(total_stmt)
    total = int(total_result.scalar_one() or 0)

    data = PaginatedResponse[CandidateRead](items=items, total=total, page=page, limit=limit)
    return success_response(data)


@router.get(
    "/{candidate_id}/related-jobs",
    response_model=APIResponse[list[RelatedJobItem]],
)
async def list_candidate_related_jobs(
    candidate_id: UUID,
    include_closed: bool = Query(False, description="Include non-open jobs"),
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user),
) -> APIResponse[list[RelatedJobItem]]:
    candidate = await session.get(Candidate, candidate_id)
    if not candidate or not candidate.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    skill_ids = set(_as_uuid_list(candidate.skills))
    edu_ids = set(_as_uuid_list(candidate.education))
    degree_ids = set(_as_uuid_list(candidate.degree))
    expected_salary = candidate.expected_salary

    # Exclude jobs already applied/interviewed
    applied_job_ids_stmt = select(Interview.job_id).where(
        Interview.candidate_id == candidate_id, Interview.is_active.is_(True)
    )
    applied_job_ids_res = await session.execute(applied_job_ids_stmt)
    applied_job_ids = {row[0] for row in applied_job_ids_res.all() if row[0]}

    filters = [Job.is_active.is_(True)]
    if not include_closed:
        filters.append(Job.status == JobStatus.OPEN.value)
    if applied_job_ids:
        filters.append(Job.id.notin_(applied_job_ids))
    if skill_ids:
        skill_subfilters = [cast(Job.skills, String).ilike(f"%{sid}%") for sid in skill_ids]
        filters.append(or_(*skill_subfilters))
    if edu_ids:
        edu_subfilters = [cast(Job.education, String).ilike(f"%{eid}%") for eid in edu_ids]
        filters.append(or_(*edu_subfilters))
    if degree_ids:
        degree_subfilters = [cast(Job.degree, String).ilike(f"%{did}%") for did in degree_ids]
        filters.append(or_(*degree_subfilters))
    if expected_salary is not None:
        filters.append(
            or_(
                and_(Job.salary_min.is_(None), Job.salary_max.is_(None)),
                and_(Job.salary_min.is_(None), Job.salary_max >= expected_salary),
                and_(Job.salary_min <= expected_salary, Job.salary_max.is_(None)),
                and_(Job.salary_min <= expected_salary, Job.salary_max >= expected_salary),
            )
        )

    stmt = (
        select(
            Job.id,
            Job.title,
            Job.company_id,
            Company.name.label("company_name"),
            MasterLocation.name.label("location_area_name"),
            Job.salary_min,
            Job.salary_max,
            Job.status,
            Job.location_area_id,
            Job.experience_level,
            Job.skills,
            Job.education,
            Job.degree,
        )
        .select_from(Job)
        .join(Company, Company.id == Job.company_id)
        .join(MasterLocation, MasterLocation.id == Job.location_area_id, isouter=True)
        .where(*filters)
        .order_by(Job.created_at.desc())
    )

    res = await session.execute(stmt)
    items: list[RelatedJobItem] = []
    for row in res.all():
        items.append(
            RelatedJobItem(
                id=row.id,
                title=row.title,
                company_id=row.company_id,
                company_name=row.company_name,
                location_area_name=row.location_area_name,
                salary_min=row.salary_min,
                salary_max=row.salary_max,
                status=row.status,
                location_area_id=row.location_area_id,
                experience_level=row.experience_level,
                skills=row.skills,
                education=row.education,
                degree=row.degree,
            )
        )

    # Fix experience_level type assignment
    for item in items:
        if item.experience_level and not isinstance(item.experience_level, ExperienceLevel):
            try:
                item.experience_level = ExperienceLevel(item.experience_level)
            except Exception:
                item.experience_level = None

    return success_response(items)


@router.post("/", response_model=APIResponse[CandidateRead])
async def create_candidate(
    body: CandidateCreate,
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin", "recruiter"])),
) -> APIResponse[CandidateRead]:
    payload = body.model_dump(exclude={"fee_structure", "initial_payment"})
    status_value = payload.get("status")
    if isinstance(status_value, CandidateStatus):
        payload["status"] = status_value.value

    fee_payload = body.fee_structure if body.status == CandidateStatus.COURSE else None
    if body.status == CandidateStatus.COURSE and fee_payload is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="fee_structure is required")

    pay_payload = body.initial_payment if body.status in {CandidateStatus.REGISTERED, CandidateStatus.COURSE} else None
    if body.status in {CandidateStatus.REGISTERED, CandidateStatus.COURSE} and pay_payload is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="initial_payment is required")

    # Compute age if dob provided
    dob_value = payload.get("dob")
    if isinstance(dob_value, date):
        today = date.today()
        payload["age"] = int((today - dob_value).days // 365)

    candidate = Candidate(**payload, is_active=True)
    session.add(candidate)

    try:
        await session.flush()

        if fee_payload is not None:
            total_fee = int(fee_payload.total_fee)
            fee_row = CourseStructureFee(
                candidate_id=candidate.id,
                total_fee=total_fee,
                balance=total_fee,
                due_date=fee_payload.due_date,
                is_active=True,
            )
            print(fee_row)
            session.add(fee_row)

        if pay_payload is not None:
            payment = CandidatePayment(
                candidate_id=candidate.id,
                amount=pay_payload.amount,
                payment_date=pay_payload.payment_date,
                remarks=pay_payload.remarks,
                is_active=True,
            )
            session.add(payment)
            if fee_payload is not None:
                fee_row.balance = max(fee_row.balance - int(pay_payload.amount), 0)

        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Candidate with this email or mobile_number already exists",
        ) from exc

    stmt = (
        select(Candidate)
        .options(
            joinedload(Candidate.location_area),
            selectinload(Candidate.fee_structure),
            selectinload(Candidate.payments),
        )
        .where(Candidate.id == candidate.id)
    )
    res = await session.execute(stmt)
    candidate_with_rels = res.scalar_one()
    hydrated = await _hydrate_candidate_with_names(session, candidate_with_rels)
    return success_response(hydrated)


@router.get("/{candidate_id}", response_model=APIResponse[CandidateRead])
async def get_candidate(
    candidate_id: UUID,
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user),
) -> APIResponse[CandidateRead]:
    stmt = (
        select(Candidate)
        .options(
            joinedload(Candidate.location_area),
            selectinload(Candidate.fee_structure),
            selectinload(Candidate.payments),
        )
        .where(Candidate.id == candidate_id)
    )
    res = await session.execute(stmt)
    candidate = res.scalar_one_or_none()
    if candidate is None or not candidate.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    count_stmt = select(func.count()).select_from(Interview).where(
        and_(Interview.is_active.is_(True), Interview.candidate_id == candidate_id)
    )
    count_res = await session.execute(count_stmt)
    interviews_count = int(count_res.scalar_one() or 0)

    if getattr(candidate, "employment_status", None) is None:
        candidate.employment_status = CandidateEmploymentStatus.UNEMPLOYED.value
    payload = await _hydrate_candidate_with_names(session, candidate)
    payload.interviews_count = interviews_count
    return success_response(payload)


@router.put("/{candidate_id}", response_model=APIResponse[CandidateRead])
async def update_candidate(
    candidate_id: UUID,
    body: CandidateUpdate,
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin", "recruiter"])),
) -> APIResponse[CandidateRead]:
    stmt = (
        select(Candidate)
        .options(
            joinedload(Candidate.location_area),
            selectinload(Candidate.fee_structure),
            selectinload(Candidate.payments),
        )
        .where(Candidate.id == candidate_id)
    )
    res = await session.execute(stmt)
    candidate = res.scalar_one_or_none()
    if candidate is None or not candidate.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    update_data = body.model_dump(exclude_unset=True, exclude={"fee_structure", "initial_payment"})
    incoming_status = update_data.get("status")
    if isinstance(incoming_status, CandidateStatus):
        update_data["status"] = incoming_status.value

    dob_value = update_data.get("dob")
    if isinstance(dob_value, date):
        today = date.today()
        update_data["age"] = int((today - dob_value).days // 365)
    elif "age" in update_data and update_data.get("age") is not None:
        # if dob not provided but age explicitly provided, keep it
        pass

    for field, value in update_data.items():
        setattr(candidate, field, value)

    effective_status = CandidateStatus(candidate.status)

    if effective_status in {CandidateStatus.FREE}:
        if body.fee_structure is not None or body.initial_payment is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="fee_structure and initial_payment are not allowed for FREE",
            )

    if effective_status == CandidateStatus.REGISTERED:
        if body.fee_structure is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="fee_structure is not allowed for REGISTERED",
            )
        if body.initial_payment is not None:
            payment = CandidatePayment(
                candidate_id=candidate.id,
                amount=body.initial_payment.amount,
                payment_date=body.initial_payment.payment_date,
                remarks=body.initial_payment.remarks,
                is_active=True,
            )
            session.add(payment)

    if effective_status == CandidateStatus.COURSE:
        print("here")
        if body.fee_structure is not None:
            print(body.fee_structure)
            if candidate.fee_structure is None:
                fee_row = CourseStructureFee(
                    candidate_id=candidate.id,
                    total_fee=int(body.fee_structure.total_fee),
                    balance=int(body.fee_structure.total_fee),
                    due_date=body.fee_structure.due_date,
                    is_active=True,
                )
                session.add(fee_row)
            else:
                candidate.fee_structure.total_fee = int(body.fee_structure.total_fee)
                candidate.fee_structure.due_date = body.fee_structure.due_date
                candidate.fee_structure.balance = int(body.fee_structure.total_fee - body.initial_payment.amount)
        if body.initial_payment is not None:
            payment = CandidatePayment(
                candidate_id=candidate.id,
                amount=body.initial_payment.amount,
                payment_date=body.initial_payment.payment_date,
                remarks=body.initial_payment.remarks,
                is_active=True,
            )
            session.add(payment)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Candidate update conflict",
        ) from exc

    await session.refresh(candidate)
    hydrated = await _hydrate_candidate_with_names(session, candidate)
    return success_response(hydrated)


@router.get("/{candidate_id}/applied-jobs", response_model=APIResponse[list[CandidateJobsReportItem]])
async def list_candidate_applied_jobs(
    candidate_id: UUID,
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user),
) -> APIResponse[list[CandidateJobsReportItem]]:
    candidate = await session.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    base_filters = [Interview.candidate_id == candidate_id]

    # grouped view of jobs with counts and last date
    job_stmt = (
        select(
            Job.id.label("job_id"),
            Job.title.label("job_title"),
            Job.company_id.label("company_id"),
            Company.name.label("company_name"),
            Job.status.label("job_status"),
            func.count(Interview.id).label("interviews_count"),
            func.max(Interview.interview_date).label("last_interview_date"),
        )
        .select_from(Interview)
        .join(Job, Job.id == Interview.job_id)
        .join(Company, Company.id == Interview.company_id)
        .where(*base_filters)
        .group_by(Job.id, Job.title, Job.company_id, Company.name, Job.status)
        .order_by(func.max(Interview.interview_date).desc())
    )
    job_res = await session.execute(job_stmt)
    rows = job_res.all()

    latest_status_by_job: dict[UUID, str] = {}
    if rows:
        job_ids = [row.job_id for row in rows]
        latest_ts_subq = (
            select(
                Interview.job_id.label("job_id"),
                func.max(Interview.interview_date).label("max_date"),
            )
            .where(*base_filters, Interview.job_id.in_(job_ids))
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
            .where(Interview.candidate_id == candidate_id)
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
    

    return success_response(items)


@router.put("/{candidate_id}/status", response_model=APIResponse[CandidateRead])
async def update_candidate_status(
    candidate_id: UUID,
    body: CandidateStatusChange,
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin", "recruiter"])),
) -> APIResponse[CandidateRead]:
    stmt = (
        select(Candidate)
        .options(
            joinedload(Candidate.location_area),
            selectinload(Candidate.fee_structure),
            selectinload(Candidate.payments),
        )
        .where(Candidate.id == candidate_id)
    )
    res = await session.execute(stmt)
    candidate = res.scalar_one_or_none()
    if candidate is None or not candidate.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    # Update status
    candidate.status = body.status.value

    # Handle fee structure and payments based on status
    if body.status in {CandidateStatus.FREE}:
        if body.fee_structure is not None or body.initial_payment is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="fee_structure and initial_payment are not allowed for FREE",
            )

    if body.status == CandidateStatus.REGISTERED:
        if body.fee_structure is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="fee_structure is not allowed for REGISTERED",
            )
        if body.initial_payment is not None:
            payment = CandidatePayment(
                candidate_id=candidate.id,
                amount=body.initial_payment.amount,
                payment_date=body.initial_payment.payment_date,
                remarks=body.initial_payment.remarks,
                is_active=True,
            )
            session.add(payment)

    if body.status == CandidateStatus.COURSE:
        if body.fee_structure is not None:
            # Calculate initial balance considering initial payment
            initial_payment_amount = int(body.initial_payment.amount) if body.initial_payment is not None else 0
            if candidate.fee_structure is None:
                fee_row = CourseStructureFee(
                    candidate_id=candidate.id,
                    total_fee=int(body.fee_structure.total_fee),
                    balance=max(int(body.fee_structure.total_fee) - initial_payment_amount, 0),
                    due_date=body.fee_structure.due_date,
                    is_active=True,
                )
                session.add(fee_row)
            else:
                candidate.fee_structure.total_fee = int(body.fee_structure.total_fee)
                candidate.fee_structure.due_date = body.fee_structure.due_date
                # Only update balance if fee structure is being modified
                if body.initial_payment is not None:
                    candidate.fee_structure.balance = max(int(body.fee_structure.total_fee) - int(body.initial_payment.amount), 0)
                else:
                    candidate.fee_structure.balance = int(body.fee_structure.total_fee)
        
        if body.initial_payment is not None:
            payment = CandidatePayment(
                candidate_id=candidate.id,
                amount=body.initial_payment.amount,
                payment_date=body.initial_payment.payment_date,
                remarks=body.initial_payment.remarks,
                is_active=True,
            )
            session.add(payment)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Candidate status update conflict",
        ) from exc

    await session.refresh(candidate)
    hydrated = await _hydrate_candidate_with_names(session, candidate)
    return success_response(hydrated)


@router.post("/{candidate_id}/upload", response_model=APIResponse[CandidateRead])
async def upload_candidate_files(
    candidate_id: UUID,
    resume: Optional[UploadFile] = FastAPIFile(None),
    photo: Optional[UploadFile] = FastAPIFile(None),
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin", "recruiter"])),
) -> APIResponse[CandidateRead]:
    candidate = await session.get(Candidate, candidate_id)
    if not candidate or not candidate.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    file_service = FileService(session)

    if resume is not None:
        resume_file = await file_service.save_upload(resume, current_user)
        candidate.resume_url = resume_file.url

    if photo is not None:
        photo_file = await file_service.save_upload(photo, current_user)
        candidate.photo_url = photo_file.url

    await session.commit()
    stmt = (
        select(Candidate)
        .options(
            joinedload(Candidate.location_area),
            selectinload(Candidate.fee_structure),
            selectinload(Candidate.payments),
        )
        .where(Candidate.id == candidate_id)
    )
    res = await session.execute(stmt)
    candidate_with_rels = res.scalar_one()
    hydrated = await _hydrate_candidate_with_names(session, candidate_with_rels)
    return success_response(hydrated)
