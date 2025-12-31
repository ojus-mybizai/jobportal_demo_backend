from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.response import APIResponse, success_response
from app.models.candidate import Candidate
from app.models.interview import Interview
from app.models.job import Job
from app.models.placement_income import PlacementIncome, PlacementIncomePayment
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.placement_income import (
    PlacementIncomeCreate,
    PlacementIncomeRead,
    PlacementIncomeUpdate,
)
from app.schemas.placement_income_payment import (
    PlacementIncomePaymentCreate,
    PlacementIncomePaymentRead,
    PlacementIncomePaymentUpdate,
)


router = APIRouter(prefix="/placement-incomes", tags=["placement_incomes"])


async def _recompute_placement_income_totals(session: AsyncSession, income: PlacementIncome) -> None:
    total_paid_stmt = select(func.coalesce(func.sum(PlacementIncomePayment.amount), 0)).where(
        PlacementIncomePayment.placement_income_id == income.id,
        PlacementIncomePayment.is_active.is_(True),
    )
    total_paid_res = await session.execute(total_paid_stmt)
    total_received = int(total_paid_res.scalar_one() or 0)
    income.total_received = total_received
    income.balance = max(0, int(income.total_receivable or 0) - total_received)


@router.post("/", response_model=APIResponse[PlacementIncomeRead])
async def create_placement_income(
    body: PlacementIncomeCreate,
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin", "recruiter"])),
) -> APIResponse[PlacementIncomeRead]:
    interview = await session.get(Interview, body.interview_id)
    if not interview or not interview.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")

    job = await session.get(Job, body.job_id)
    if not job or not job.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    candidate = await session.get(Candidate, body.candidate_id)
    if not candidate or not candidate.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    if interview.job_id != body.job_id or interview.candidate_id != body.candidate_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Interview does not match candidate_id/job_id",
        )

    income = PlacementIncome(
        interview_id=body.interview_id,
        candidate_id=body.candidate_id,
        job_id=body.job_id,
        total_receivable=body.total_receivable,
        due_date=body.due_date,
        remarks=body.remarks,
        is_active=True,
        total_received=0,
        balance=int(body.total_receivable or 0),
    )
    session.add(income)
    await session.commit()
    await session.refresh(income)
    return success_response(PlacementIncomeRead.model_validate(income))


@router.get("/", response_model=APIResponse[PaginatedResponse[PlacementIncomeRead]])
async def list_placement_incomes(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    interview_id: Optional[UUID] = Query(None),
    candidate_id: Optional[UUID] = Query(None),
    job_id: Optional[UUID] = Query(None),
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user),
) -> APIResponse[PaginatedResponse[PlacementIncomeRead]]:
    filters = [PlacementIncome.is_active.is_(True)]
    if interview_id is not None:
        filters.append(PlacementIncome.interview_id == interview_id)
    if candidate_id is not None:
        filters.append(PlacementIncome.candidate_id == candidate_id)
    if job_id is not None:
        filters.append(PlacementIncome.job_id == job_id)

    stmt = select(PlacementIncome).where(and_(*filters)).order_by(PlacementIncome.created_at.desc())
    stmt = stmt.limit(limit).offset((page - 1) * limit)

    total_stmt = select(func.count()).select_from(PlacementIncome).where(and_(*filters))

    res = await session.execute(stmt)
    items = [PlacementIncomeRead.model_validate(x) for x in res.scalars().all()]

    total_res = await session.execute(total_stmt)
    total = int(total_res.scalar_one() or 0)

    return success_response(PaginatedResponse[PlacementIncomeRead](items=items, total=total, page=page, limit=limit))


@router.get("/{income_id}", response_model=APIResponse[PlacementIncomeRead])
async def get_placement_income(
    income_id: UUID,
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user),
) -> APIResponse[PlacementIncomeRead]:
    income = await session.get(PlacementIncome, income_id)
    if not income or not income.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Placement income not found")
    return success_response(PlacementIncomeRead.model_validate(income))


@router.put("/{income_id}", response_model=APIResponse[PlacementIncomeRead])
async def update_placement_income(
    income_id: UUID,
    body: PlacementIncomeUpdate,
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin", "recruiter"])),
) -> APIResponse[PlacementIncomeRead]:
    income = await session.get(PlacementIncome, income_id)
    if not income or not income.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Placement income not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(income, field, value)

    # Ensure referenced records are still consistent/active
    interview = await session.get(Interview, income.interview_id)
    if not interview or not interview.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")
    if interview.job_id != income.job_id or interview.candidate_id != income.candidate_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Interview does not match candidate_id/job_id",
        )
    job = await session.get(Job, income.job_id)
    if not job or not job.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    candidate = await session.get(Candidate, income.candidate_id)
    if not candidate or not candidate.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    await _recompute_placement_income_totals(session, income)

    await session.commit()
    await session.refresh(income)
    return success_response(PlacementIncomeRead.model_validate(income))


@router.post(
    "/{income_id}/payments",
    response_model=APIResponse[PlacementIncomePaymentRead],
)
async def create_placement_income_payment(
    income_id: UUID,
    body: PlacementIncomePaymentCreate,
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin", "recruiter"])),
) -> APIResponse[PlacementIncomePaymentRead]:
    income = await session.get(PlacementIncome, income_id)
    if not income or not income.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Placement income not found")

    payment = PlacementIncomePayment(
        placement_income_id=income.id,
        amount=body.amount,
        paid_date=body.paid_date,
        remarks=body.remarks,
        is_active=True,
    )
    session.add(payment)
    await session.flush()

    await _recompute_placement_income_totals(session, income)

    await session.commit()
    await session.refresh(payment)
    return success_response(PlacementIncomePaymentRead.model_validate(payment))


@router.get(
    "/{income_id}/payments",
    response_model=APIResponse[list[PlacementIncomePaymentRead]],
)
async def list_placement_income_payments(
    income_id: UUID,
    include_inactive: bool = Query(False),
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user),
) -> APIResponse[list[PlacementIncomePaymentRead]]:
    income = await session.get(PlacementIncome, income_id)
    if not income or not income.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Placement income not found")

    filters = [PlacementIncomePayment.placement_income_id == income_id]
    if not include_inactive:
        filters.append(PlacementIncomePayment.is_active.is_(True))

    stmt = (
        select(PlacementIncomePayment)
        .where(and_(*filters))
        .order_by(PlacementIncomePayment.paid_date.desc(), PlacementIncomePayment.created_at.desc())
    )
    res = await session.execute(stmt)
    items = [PlacementIncomePaymentRead.model_validate(x) for x in res.scalars().all()]
    return success_response(items)


@router.put(
    "/payments/{payment_id}",
    response_model=APIResponse[PlacementIncomePaymentRead],
)
async def update_placement_income_payment(
    payment_id: UUID,
    body: PlacementIncomePaymentUpdate,
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin", "recruiter"])),
) -> APIResponse[PlacementIncomePaymentRead]:
    payment = await session.get(PlacementIncomePayment, payment_id)
    if not payment or not payment.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Placement income payment not found")

    income = await session.get(PlacementIncome, payment.placement_income_id)
    if not income or not income.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Placement income not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(payment, field, value)

    await _recompute_placement_income_totals(session, income)

    await session.commit()
    await session.refresh(payment)
    return success_response(PlacementIncomePaymentRead.model_validate(payment))


@router.delete(
    "/payments/{payment_id}",
    response_model=APIResponse[PlacementIncomePaymentRead],
)
async def delete_placement_income_payment(
    payment_id: UUID,
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin"])),
) -> APIResponse[PlacementIncomePaymentRead]:
    payment = await session.get(PlacementIncomePayment, payment_id)
    if not payment or not payment.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Placement income payment not found")

    income = await session.get(PlacementIncome, payment.placement_income_id)
    if not income or not income.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Placement income not found")

    payment.is_active = False

    await _recompute_placement_income_totals(session, income)

    await session.commit()
    await session.refresh(payment)
    return success_response(PlacementIncomePaymentRead.model_validate(payment))


@router.delete("/{income_id}", response_model=APIResponse[PlacementIncomeRead])
async def delete_placement_income(
    income_id: UUID,
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin"])),
) -> APIResponse[PlacementIncomeRead]:
    income = await session.get(PlacementIncome, income_id)
    if not income or not income.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Placement income not found")

    income.is_active = False
    await session.commit()
    await session.refresh(income)
    return success_response(PlacementIncomeRead.model_validate(income))
