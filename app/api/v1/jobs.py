from typing import List, Optional
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File as FastAPIFile, HTTPException, Query, UploadFile, status
from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.api import deps
from app.core.response import APIResponse, success_response
from app.models.candidate import Candidate
from app.models.interview import Interview
from app.models.job import Job, JobStatus, JobType, Gender, Joined_candidates
from app.models.master import MasterDegree, MasterEducation, MasterJobCategory, MasterSkill, MasterLocation
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.job import JobCreate, JobRead, JobStatusUpdate, JobUpdate, RelatedCandidateItem
from app.services.file_service import FileService


router = APIRouter(prefix="/jobs", tags=["jobs"])


async def _fetch_name_map(session: AsyncSession, model, ids: set[UUID]) -> dict[UUID, str]:
    if not ids:
        return {}
    stmt = select(model.id, model.name).where(model.id.in_(ids))
    res = await session.execute(stmt)
    return {row[0]: row[1] for row in res.all()}


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


@router.get(
    "/{job_id}/related-candidates",
    response_model=APIResponse[list[RelatedCandidateItem]],
)
async def list_job_related_candidates(
    job_id: UUID,
    include_inactive_candidates: bool = Query(False),
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user),
) -> APIResponse[list[RelatedCandidateItem]]:
    job = await session.get(Job, job_id)
    if not job or not job.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    # Collect job attributes
    job_skill_ids = set(_as_uuid_list(job.skills))
    job_edu_ids = set(_as_uuid_list(job.education))
    job_degree_ids = set(_as_uuid_list(job.degree))
    salary_min = job.salary_min
    salary_max = job.salary_max

    # Exclude candidates already interviewed for this job
    interviewed_stmt = select(Interview.candidate_id).where(
        Interview.job_id == job_id,
        Interview.is_active.is_(True),
    )
    interviewed_res = await session.execute(interviewed_stmt)
    interviewed_ids = {row[0] for row in interviewed_res.all() if row[0]}

    filters = [Candidate.is_active.is_(True)] if not include_inactive_candidates else []
    if interviewed_ids:
        filters.append(Candidate.id.notin_(interviewed_ids))
    if job_skill_ids:
        skill_subfilters = [cast(Candidate.skills, String).ilike(f"%{sid}%") for sid in job_skill_ids]
        filters.append(or_(*skill_subfilters))
    if job_edu_ids:
        edu_subfilters = [cast(Candidate.education, String).ilike(f"%{eid}%") for eid in job_edu_ids]
        filters.append(or_(*edu_subfilters))
    if job_degree_ids:
        degree_subfilters = [cast(Candidate.degree, String).ilike(f"%{did}%") for did in job_degree_ids]
        filters.append(or_(*degree_subfilters))

    if salary_min is not None or salary_max is not None:
        salary_filters = []
        if salary_min is not None:
            salary_filters.append(
                or_(
                    Candidate.expected_salary.is_(None),
                    Candidate.expected_salary >= salary_min,
                )
            )
        if salary_max is not None:
            salary_filters.append(
                or_(
                    Candidate.expected_salary.is_(None),
                    Candidate.expected_salary <= salary_max,
                )
            )
        filters.extend(salary_filters)

    stmt = (
        select(
            Candidate.id,
            Candidate.full_name,
            Candidate.email,
            Candidate.mobile_number,
            MasterLocation.name.label("location_area_name"),
            Candidate.expected_salary,
            Candidate.status,
            Candidate.experience_level,
            Candidate.location_area_id,
            Candidate.skills,
            Candidate.education,
            Candidate.degree,
        )
        .select_from(Candidate)
        .join(MasterLocation, MasterLocation.id == Candidate.location_area_id, isouter=True)
        .where(*filters)
        .order_by(Candidate.created_at.desc())
    )

    res = await session.execute(stmt)
    items: list[RelatedCandidateItem] = []
    for row in res.all():
        items.append(
            RelatedCandidateItem(
                id=row.id,
                full_name=row.full_name,
                email=row.email,
                mobile_number=row.mobile_number,
                location_area_name=row.location_area_name,
                expected_salary=row.expected_salary,
                status=row.status,
                experience_level=row.experience_level,
                location_area_id=row.location_area_id,
                skills=row.skills,
                education=row.education,
                degree=row.degree,
            )
        )

    return success_response(items)


async def _hydrate_job_with_names(session: AsyncSession, job: Job) -> JobRead:
    category_map = await _fetch_name_map(session, MasterJobCategory, set(_as_uuid_list(job.job_categories)))
    skill_map = await _fetch_name_map(session, MasterSkill, set(_as_uuid_list(job.skills)))
    education_map = await _fetch_name_map(session, MasterEducation, set(_as_uuid_list(job.education)))
    degree_map = await _fetch_name_map(session, MasterDegree, set(_as_uuid_list(job.degree)))
    location_map = await _fetch_name_map(
        session, MasterLocation, {job.location_area_id} if job.location_area_id else set()
    )
    payload = JobRead.model_validate(job)
    payload.job_category_names = [category_map.get(x) for x in _as_uuid_list(job.job_categories) if category_map.get(x)]
    payload.skill_names = [skill_map.get(x) for x in _as_uuid_list(job.skills) if skill_map.get(x)]
    payload.education_names = [education_map.get(x) for x in _as_uuid_list(job.education) if education_map.get(x)]
    payload.degree_names = [degree_map.get(x) for x in _as_uuid_list(job.degree) if degree_map.get(x)]
    payload.location_area_name = location_map.get(job.location_area_id) if job.location_area_id else None
    return payload


@router.get("/", response_model=APIResponse[PaginatedResponse[JobRead]])
async def list_jobs(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    company_id: Optional[UUID] = Query(None),
    status_filter: Optional[JobStatus] = Query(None, alias="status"),
    job_type: Optional[JobType] = Query(None),
    gender: Optional[Gender] = Query(None),
    location_area_id: Optional[UUID] = Query(None),
    min_salary: Optional[int] = Query(None, ge=0),
    max_salary: Optional[int] = Query(None, ge=0),
    vacancies_min: Optional[int] = Query(None, ge=0),
    vacancies_max: Optional[int] = Query(None, ge=0),
    skills: Optional[List[str]] = Query(None),
    q: Optional[str] = Query(None, description="Search in title and description"),
    created_from: Optional[datetime] = Query(None),
    created_to: Optional[datetime] = Query(None),
    is_active: Optional[bool] = Query(True),
    sort_by: Optional[str] = Query("created_at"),
    order: Optional[str] = Query("desc"),
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user),
) -> APIResponse[PaginatedResponse[JobRead]]:
    stmt = select(Job).options(
        joinedload(Job.company),
        joinedload(Job.joined_candidates).joinedload(Joined_candidates.candidate),
        joinedload(Job.location_area),
    )
    filters = []

    if is_active is not None:
        filters.append(Job.is_active.is_(is_active))

    if company_id:
        filters.append(Job.company_id == company_id)
    if status_filter:
        filters.append(Job.status == status_filter.value)
    if job_type is not None:
        filters.append(Job.job_type == job_type.value)
    if gender is not None:
        filters.append(Job.gender == gender.value)
    if location_area_id:
        filters.append(Job.location_area_id == location_area_id)
    if min_salary is not None:
        filters.append(Job.salary_min >= min_salary)
    if max_salary is not None:
        filters.append(Job.salary_max <= max_salary)
    if vacancies_min is not None:
        filters.append(Job.num_vacancies >= vacancies_min)
    if vacancies_max is not None:
        filters.append(Job.num_vacancies <= vacancies_max)
    if skills:
        filters.append(Job.skills.contains(skills))
    if q:
        like = f"%{q}%"
        filters.append(or_(Job.title.ilike(like), Job.description.ilike(like)))
    if created_from is not None:
        filters.append(Job.created_at >= created_from)
    if created_to is not None:
        filters.append(Job.created_at <= created_to)

    if filters:
        stmt = stmt.where(and_(*filters))

    allowed_sort_fields = {
        "created_at": Job.created_at,
        "updated_at": Job.updated_at,
        "title": Job.title,
        "status": Job.status,
        "salary_min": Job.salary_min,
        "salary_max": Job.salary_max,
        "num_vacancies": Job.num_vacancies,
    }
    if sort_by not in allowed_sort_fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid sort_by. Allowed: {', '.join(sorted(allowed_sort_fields.keys()))}",
        )
    sort_attr = allowed_sort_fields[sort_by]
    normalized_order = (order or "desc").strip().lower()
    if normalized_order not in {"asc", "desc"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="order must be either 'asc' or 'desc'",
        )
    stmt = stmt.order_by(sort_attr.asc() if normalized_order == "asc" else sort_attr.desc())

    stmt = stmt.limit(limit).offset((page - 1) * limit)

    total_stmt = select(func.count()).select_from(Job)
    if filters:
        total_stmt = total_stmt.where(and_(*filters))

    result = (await session.execute(stmt)).unique()
    jobs = result.scalars().all()
    # collect master ids
    category_ids: set[UUID] = set()
    skill_ids: set[UUID] = set()
    education_ids: set[UUID] = set()
    degree_ids: set[UUID] = set()
    for job in jobs:
        category_ids.update(_as_uuid_list(job.job_categories))
        skill_ids.update(_as_uuid_list(job.skills))
        education_ids.update(_as_uuid_list(job.education))
        degree_ids.update(_as_uuid_list(job.degree))

    category_map = await _fetch_name_map(session, MasterJobCategory, category_ids)
    skill_map = await _fetch_name_map(session, MasterSkill, skill_ids)
    education_map = await _fetch_name_map(session, MasterEducation, education_ids)
    degree_map = await _fetch_name_map(session, MasterDegree, degree_ids)
    location_ids = {job.location_area_id for job in jobs if job.location_area_id}
    location_map = await _fetch_name_map(session, MasterLocation, set(location_ids))

    items: list[JobRead] = []
    for job in jobs:
        payload = JobRead.model_validate(job)
        payload.job_category_names = [category_map.get(x) for x in _as_uuid_list(job.job_categories) if category_map.get(x)]
        payload.skill_names = [skill_map.get(x) for x in _as_uuid_list(job.skills) if skill_map.get(x)]
        payload.education_names = [education_map.get(x) for x in _as_uuid_list(job.education) if education_map.get(x)]
        payload.degree_names = [degree_map.get(x) for x in _as_uuid_list(job.degree) if degree_map.get(x)]
        payload.location_area_name = location_map.get(job.location_area_id) if job.location_area_id else None
        items.append(payload)

    total_result = await session.execute(total_stmt)
    total = int(total_result.scalar_one() or 0)

    job_ids = [job.id for job in jobs]
    counts_by_job: dict[UUID, int] = {}
    if job_ids:
        counts_stmt = (
            select(Interview.job_id, func.count())
            .where(and_(Interview.is_active.is_(True), Interview.job_id.in_(job_ids)))
            .group_by(Interview.job_id)
        )
        counts_res = await session.execute(counts_stmt)
        counts_by_job = {row[0]: int(row[1] or 0) for row in counts_res.all()}

    items = []
    for job in jobs:
        payload = JobRead.model_validate(job)
        payload.interviews_count = counts_by_job.get(job.id, 0)
        items.append(payload)

    data = PaginatedResponse[JobRead](items=items, total=total, page=page, limit=limit)
    return success_response(data)


@router.post("/", response_model=APIResponse[JobRead])
async def create_job(
    body: JobCreate,
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin", "recruiter"])),
) -> APIResponse[JobRead]:
    job_data = body.model_dump()
    status_value = job_data.pop("status", JobStatus.OPEN)

    job_type_value = job_data.get("job_type")
    if isinstance(job_type_value, JobType):
        job_data["job_type"] = job_type_value.value

    job = Job(
        **job_data,
        status=status_value.value,
    )
    session.add(job)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job creation conflict",
        ) from exc
    stmt = (
        select(Job)
        .options(
            joinedload(Job.company),
            joinedload(Job.joined_candidates).joinedload(Joined_candidates.candidate),
            joinedload(Job.location_area),
        )
        .where(Job.id == job.id)
    )
    result = (await session.execute(stmt)).unique()
    job_with_rels = result.scalar_one()
    hydrated = await _hydrate_job_with_names(session, job_with_rels)
    return success_response(hydrated)


@router.get("/{job_id}", response_model=APIResponse[JobRead])
async def get_job(
    job_id: UUID,
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user),
) -> APIResponse[JobRead]:
    stmt = (
        select(Job)
        .options(
            joinedload(Job.company),
            joinedload(Job.joined_candidates).joinedload(Joined_candidates.candidate),
            joinedload(Job.location_area),
        )
        .where(Job.id == job_id)
    )
    result = (await session.execute(stmt)).unique()
    job = result.scalar_one_or_none()
    if job is None or not job.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    category_map = await _fetch_name_map(session, MasterJobCategory, set(_as_uuid_list(job.job_categories)))
    skill_map = await _fetch_name_map(session, MasterSkill, set(_as_uuid_list(job.skills)))
    education_map = await _fetch_name_map(session, MasterEducation, set(_as_uuid_list(job.education)))
    degree_map = await _fetch_name_map(session, MasterDegree, set(_as_uuid_list(job.degree)))
    location_map = await _fetch_name_map(session, MasterLocation, {job.location_area_id} if job.location_area_id else set())

    count_stmt = select(func.count()).select_from(Interview).where(
        and_(Interview.is_active.is_(True), Interview.job_id == job_id)
    )
    count_res = await session.execute(count_stmt)
    interviews_count = int(count_res.scalar_one() or 0)

    payload = JobRead.model_validate(job)
    payload.job_category_names = [category_map.get(x) for x in _as_uuid_list(job.job_categories) if category_map.get(x)]
    payload.skill_names = [skill_map.get(x) for x in _as_uuid_list(job.skills) if skill_map.get(x)]
    payload.education_names = [education_map.get(x) for x in _as_uuid_list(job.education) if education_map.get(x)]
    payload.degree_names = [degree_map.get(x) for x in _as_uuid_list(job.degree) if degree_map.get(x)]
    payload.location_area_name = location_map.get(job.location_area_id) if job.location_area_id else None
    payload.interviews_count = interviews_count
    return success_response(payload)


@router.put("/{job_id}", response_model=APIResponse[JobRead])
async def update_job(
    job_id: UUID,
    body: JobUpdate,
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin", "recruiter"])),
) -> APIResponse[JobRead]:
    stmt = (
        select(Job)
        .options(
            joinedload(Job.company),
            joinedload(Job.joined_candidates).joinedload(Joined_candidates.candidate),
            joinedload(Job.location_area),
        )
        .where(Job.id == job_id)
    )
    result = (await session.execute(stmt)).unique()
    job = result.scalar_one_or_none()
    if job is None or not job.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    update_data = body.model_dump(exclude_unset=True)
    status_value = update_data.pop("status", None)
    for field, value in update_data.items():
        if field == "job_type" and isinstance(value, JobType):
            value = value.value
        setattr(job, field, value)
    if status_value is not None:
        job.status = status_value.value

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job update conflict",
        ) from exc
    stmt = (
        select(Job)
        .options(
            joinedload(Job.company),
            joinedload(Job.joined_candidates).joinedload(Joined_candidates.candidate),
            joinedload(Job.location_area),
        )
        .where(Job.id == job_id)
    )
    result = (await session.execute(stmt)).unique()
    job_with_rels = result.scalar_one()
    hydrated = await _hydrate_job_with_names(session, job_with_rels)
    return success_response(hydrated)


@router.patch("/{job_id}/status", response_model=APIResponse[JobRead])
async def update_job_status(
    job_id: UUID,
    body: JobStatusUpdate,
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin", "recruiter"])),
) -> APIResponse[JobRead]:
    stmt = (
        select(Job)
        .options(
            joinedload(Job.company),
            joinedload(Job.joined_candidates).joinedload(Joined_candidates.candidate),
            joinedload(Job.location_area),
        )
        .where(Job.id == job_id)
    )
    result = (await session.execute(stmt)).unique()
    job = result.scalar_one_or_none()
    if job is None or not job.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    job.status = body.status.value
    await session.commit()
    stmt = (
        select(Job)
        .options(
            joinedload(Job.company),
            joinedload(Job.joined_candidates).joinedload(Joined_candidates.candidate),
            joinedload(Job.location_area),
        )
        .where(Job.id == job_id)
    )
    result = (await session.execute(stmt)).unique()
    job_with_rels = result.scalar_one()
    hydrated = await _hydrate_job_with_names(session, job_with_rels)
    return success_response(hydrated)


@router.post("/{job_id}/attachments", response_model=APIResponse[JobRead])
async def upload_job_attachments(
    job_id: UUID,
    files: List[UploadFile] = FastAPIFile(...),
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin", "recruiter"])),
) -> APIResponse[JobRead]:
    stmt = (
        select(Job)
        .options(
            joinedload(Job.company),
            joinedload(Job.joined_candidates).joinedload(Joined_candidates.candidate),
            joinedload(Job.location_area),
        )
        .where(Job.id == job_id)
    )
    result = (await session.execute(stmt)).unique()
    job = result.scalar_one_or_none()
    if job is None or not job.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    file_service = FileService(session)

    attachments = list(job.attachments or [])
    for upload in files:
        stored = await file_service.save_upload(upload, current_user)
        attachments.append(stored.url)

    job.attachments = attachments

    await session.commit()
    stmt = (
        select(Job)
        .options(
            joinedload(Job.company),
            joinedload(Job.joined_candidates).joinedload(Joined_candidates.candidate),
            joinedload(Job.location_area),
        )
        .where(Job.id == job_id)
    )
    result = (await session.execute(stmt)).unique()
    job_with_rels = result.scalar_one()
    hydrated = await _hydrate_job_with_names(session, job_with_rels)
    return success_response(hydrated)
