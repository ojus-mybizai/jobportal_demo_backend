from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.response import APIResponse, success_response
from app.models.candidate import Candidate, CandidatePayment, CandidateStatus
from app.models.user import User
from app.schemas.candidate_payment import CandidatePaymentCreate, CandidatePaymentRead


router = APIRouter(tags=["candidate_payments"])


async def _recompute_joc_fee_balance(session: AsyncSession, candidate: Candidate) -> None:
    if CandidateStatus(candidate.status) != CandidateStatus.JOC:
        return
    fee = candidate.fee_structure
    if fee is None or not fee.is_active:
        return
    total_paid_stmt = select(func.coalesce(func.sum(CandidatePayment.amount), 0)).where(
        CandidatePayment.candidate_id == candidate.id,
        CandidatePayment.is_active.is_(True),
    )
    total_paid_res = await session.execute(total_paid_stmt)
    total_paid = int(total_paid_res.scalar_one() or 0)
    fee.balance = int(fee.total_fee or 0) - total_paid


@router.post(
    "/candidates/{candidate_id}/payments",
    response_model=APIResponse[CandidatePaymentRead],
)
async def create_candidate_payment(
    candidate_id: UUID,
    body: CandidatePaymentCreate,
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin", "recruiter"])),
) -> APIResponse[CandidatePaymentRead]:
    candidate = await session.get(Candidate, candidate_id)
    if not candidate or not candidate.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    cand_status = CandidateStatus(candidate.status)
    if cand_status in {CandidateStatus.CAPS, CandidateStatus.FREE}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payments are not allowed for CAPS/FREE candidates",
        )
    if cand_status == CandidateStatus.JOC:
        if candidate.fee_structure is None or not candidate.fee_structure.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="fee_structure is required before taking payment for JOC candidates",
            )

    payment = CandidatePayment(
        candidate_id=candidate.id,
        amount=body.amount,
        payment_date=body.payment_date,
        remarks=body.remarks,
        is_active=True,
    )
    session.add(payment)
    await session.flush()

    await _recompute_joc_fee_balance(session, candidate)

    await session.commit()
    await session.refresh(payment)
    return success_response(CandidatePaymentRead.model_validate(payment))


@router.put(
    "/candidate-payments/{payment_id}",
    response_model=APIResponse[CandidatePaymentRead],
)
async def update_candidate_payment(
    payment_id: UUID,
    body: CandidatePaymentCreate,
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin", "recruiter"])),
) -> APIResponse[CandidatePaymentRead]:
    payment = await session.get(CandidatePayment, payment_id)
    if not payment or not payment.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate payment not found")

    candidate = await session.get(Candidate, payment.candidate_id)
    if not candidate or not candidate.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    payment.amount = body.amount
    payment.payment_date = body.payment_date
    payment.remarks = body.remarks

    await _recompute_joc_fee_balance(session, candidate)

    await session.commit()
    await session.refresh(payment)
    return success_response(CandidatePaymentRead.model_validate(payment))


async def _recompute_candidate_balance(session, candidate):
    await _recompute_joc_fee_balance(session, candidate)


@router.get(
    "/candidates/{candidate_id}/payments",
    response_model=APIResponse[list[CandidatePaymentRead]],
)
async def get_candidate_payments(
    candidate_id: UUID,
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user),
) -> APIResponse[list[CandidatePaymentRead]]:
    candidate = await session.get(Candidate, candidate_id)
    if not candidate or not candidate.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    stmt = (
        select(CandidatePayment)
        .where(
            CandidatePayment.candidate_id == candidate_id,
            CandidatePayment.is_active.is_(True),
        )
        .order_by(CandidatePayment.payment_date.desc(), CandidatePayment.created_at.desc())
    )
    res = await session.execute(stmt)
    items = [CandidatePaymentRead.model_validate(x) for x in res.scalars().all()]
    return success_response(items)


@router.delete(
    "/candidate-payments/{payment_id}",
    response_model=APIResponse[CandidatePaymentRead],
)
async def delete_candidate_payment(
    payment_id: UUID,
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin"])),
) -> APIResponse[CandidatePaymentRead]:
    payment = await session.get(CandidatePayment, payment_id)
    if not payment or not payment.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate payment not found")

    candidate = await session.get(Candidate, payment.candidate_id)
    if not candidate or not candidate.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    payment.is_active = False

    await _recompute_joc_fee_balance(session, candidate)

    await session.commit()
    await session.refresh(payment)
    return success_response(CandidatePaymentRead.model_validate(payment))

