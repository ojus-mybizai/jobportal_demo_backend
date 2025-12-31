from typing import Optional
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File as FastAPIFile, HTTPException, Query, UploadFile, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.api import deps
from app.core.response import APIResponse, success_response
from app.models.company import Company, CompanyPayment
from app.models.master import MasterCompanyCategory, MasterLocation
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.company import (
    CompanyCreate,
    CompanyPaymentCreate,
    CompanyPaymentRead,
    CompanyRead,
    CompanyUpdate,
)
from app.services.file_service import FileService


router = APIRouter(prefix="/companies", tags=["companies"])


async def _validate_master_active(
    session: AsyncSession,
    model,
    item_id: UUID | None,
    field_name: str,
) -> None:
    if item_id is None:
        return
    obj = await session.get(model, item_id)
    if not obj:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name}",
        )

    is_active = getattr(obj, "is_active", None)
    if is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid or inactive {field_name}",
        )


async def _get_company_for_read(session: AsyncSession, company_id: UUID) -> Company:
    result = await session.execute(
        select(Company)
        .options(
            joinedload(Company.category),
            joinedload(Company.location_area),
            selectinload(Company.payments),
        )
        .where(Company.id == company_id)
    )
    company = result.scalar_one_or_none()
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


@router.get("/", response_model=APIResponse[PaginatedResponse[CompanyRead]])
async def list_companies(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    q: Optional[str] = Query(None, description="Search in name and contact_person"),
    category_id: Optional[UUID] = Query(None),
    location_area_id: Optional[UUID] = Query(None),
    created_by: Optional[UUID] = Query(None),
    email: Optional[str] = Query(None),
    contact_number: Optional[str] = Query(None),
    verification_status: Optional[bool] = Query(None),
    is_verified: Optional[bool] = Query(None, alias="is_verified"),
    company_status: Optional[str] = Query(None),
    created_from: Optional[datetime] = Query(None),
    created_to: Optional[datetime] = Query(None),
    is_active: Optional[bool] = Query(True),
    sort_by: str = Query("created_at"),
    order: str = Query("desc"),
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user),
) -> APIResponse[PaginatedResponse[CompanyRead]]:
    stmt = select(Company).options(
        joinedload(Company.category),
        joinedload(Company.location_area),
        selectinload(Company.payments),
    )
    filters = []

    if is_active is not None:
        filters.append(Company.is_active.is_(is_active))
    effective_verification_status = (
        verification_status if verification_status is not None else is_verified
    )
    if effective_verification_status is not None:
        filters.append(Company.verification_status.is_(effective_verification_status))
    if company_status is not None:
        normalized_company_status = company_status.strip().upper()
        if normalized_company_status not in {"FREE", "PAID"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="company_status must be either 'FREE' or 'PAID'",
            )
        filters.append(Company.company_status == normalized_company_status)
    if category_id:
        filters.append(Company.category_id == category_id)
    if location_area_id:
        filters.append(Company.location_area_id == location_area_id)
    if created_by is not None:
        filters.append(Company.created_by == created_by)
    if email:
        filters.append(Company.email.ilike(email.strip()))
    if contact_number:
        filters.append(Company.contact_number.ilike(contact_number.strip()))
    if q:
        like = f"%{q}%"
        filters.append(or_(Company.name.ilike(like), Company.contact_person.ilike(like)))
    if created_from is not None:
        filters.append(Company.created_at >= created_from)
    if created_to is not None:
        filters.append(Company.created_at <= created_to)

    if filters:
        stmt = stmt.where(and_(*filters))

    allowed_sort_fields = {
        "created_at": Company.created_at,
        "updated_at": Company.updated_at,
        "name": Company.name,
        "company_status": Company.company_status,
        "verification_status": Company.verification_status,
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

    total_stmt = select(func.count()).select_from(Company)
    if filters:
        total_stmt = total_stmt.where(and_(*filters))

    result = await session.execute(stmt)
    companies = result.scalars().all()
    items = [CompanyRead.model_validate(obj) for obj in companies]

    total_result = await session.execute(total_stmt)
    total = int(total_result.scalar_one() or 0)

    data = PaginatedResponse[CompanyRead](items=items, total=total, page=page, limit=limit)
    return success_response(data)


@router.post("/", response_model=APIResponse[CompanyRead])
async def create_company(
    body: CompanyCreate,
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin", "recruiter"])),
) -> APIResponse[CompanyRead]:
    data = body.model_dump()
    payments_data = data.pop("payments", []) or []

    await _validate_master_active(
        session,
        MasterCompanyCategory,
        data.get("category_id"),
        "category_id",
    )
    await _validate_master_active(
        session,
        MasterLocation,
        data.get("location_area_id"),
        "location_area_id",
    )

    company = Company(
        **data,
        created_by=current_user.id,
    )

    for payment_data in payments_data:
        company.payments.append(CompanyPayment(**payment_data))
    session.add(company)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Company creation conflict",
        ) from exc
    company_for_read = await _get_company_for_read(session, company.id)
    return success_response(CompanyRead.model_validate(company_for_read))


@router.get("/{company_id}", response_model=APIResponse[CompanyRead])
async def get_company(
    company_id: UUID,
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user),
) -> APIResponse[CompanyRead]:
    result = await session.execute(
        select(Company)
        .options(
            joinedload(Company.category),
            joinedload(Company.location_area),
            selectinload(Company.payments),
        )
        .where(Company.id == company_id)
    )
    company = result.scalar_one_or_none()
    if not company or not company.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return success_response(CompanyRead.model_validate(company))


@router.put("/{company_id}", response_model=APIResponse[CompanyRead])
async def update_company(
    company_id: UUID,
    body: CompanyUpdate,
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin", "recruiter"])),
) -> APIResponse[CompanyRead]:
    company = await session.get(Company, company_id)
    if not company or not company.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    update_data = body.model_dump(exclude_unset=True)
    payments_data = update_data.pop("payments", None)

    if "category_id" in update_data:
        await _validate_master_active(
            session,
            MasterCompanyCategory,
            update_data.get("category_id"),
            "category_id",
        )
    if "location_area_id" in update_data:
        await _validate_master_active(
            session,
            MasterLocation,
            update_data.get("location_area_id"),
            "location_area_id",
        )

    for field, value in update_data.items():
        setattr(company, field, value)

    if payments_data:
        for payment_data in payments_data:
            company.payments.append(CompanyPayment(**payment_data))

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Company update conflict",
        ) from exc
    company_for_read = await _get_company_for_read(session, company.id)
    return success_response(CompanyRead.model_validate(company_for_read))


@router.delete("/{company_id}", response_model=APIResponse[CompanyRead])
async def delete_company(
    company_id: UUID,
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin"])),
) -> APIResponse[CompanyRead]:
    company = await session.get(Company, company_id)
    if not company or not company.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    company.is_active = False
    await session.commit()
    company_for_read = await _get_company_for_read(session, company.id)
    return success_response(CompanyRead.model_validate(company_for_read))


@router.post("/{company_id}/payments", response_model=APIResponse[CompanyPaymentRead])
async def create_company_payment(
    company_id: UUID,
    body: CompanyPaymentCreate,
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin", "recruiter"])),
) -> APIResponse[CompanyPaymentRead]:
    company = await session.get(Company, company_id)
    if not company or not company.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    payment = CompanyPayment(
        company_id=company.id,
        amount=body.amount,
        payment_date=body.payment_date,
    )
    session.add(payment)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payment creation conflict",
        ) from exc
    await session.refresh(payment)
    return success_response(CompanyPaymentRead.model_validate(payment))


@router.post("/{company_id}/upload", response_model=APIResponse[CompanyRead])
async def upload_company_files(
    company_id: UUID,
    visiting_card: Optional[UploadFile] = FastAPIFile(None),
    front_image: Optional[UploadFile] = FastAPIFile(None),
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin", "recruiter"])),
) -> APIResponse[CompanyRead]:
    company = await session.get(Company, company_id)
    if not company or not company.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    file_service = FileService(session)

    if visiting_card is not None:
        visiting_card_file = await file_service.save_upload(visiting_card, current_user)
        company.visiting_card_url = visiting_card_file.url

    if front_image is not None:
        front_image_file = await file_service.save_upload(front_image, current_user)
        company.front_image_url = front_image_file.url

    await session.commit()
    company_for_read = await _get_company_for_read(session, company.id)
    return success_response(CompanyRead.model_validate(company_for_read))
