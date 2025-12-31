from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.api import deps
from app.core.response import APIResponse, success_response
from app.models.company import Company
from app.schemas.company import CompanyPublicRead


router = APIRouter(prefix="/public", tags=["public"])


@router.get("/company/{user_id}/{company_id}", response_model=APIResponse[CompanyPublicRead])
async def public_company_detail(
    user_id: UUID,
    company_id: UUID,
    session: AsyncSession = Depends(deps.get_db_session),
) -> APIResponse[CompanyPublicRead]:
    result = await session.execute(
        select(Company)
        .options(
            joinedload(Company.category),
            joinedload(Company.location_area),
        )
        .where(
            and_(
                Company.id == company_id,
                Company.created_by == user_id,
                Company.is_active.is_(True),
            )
        )
    )
    company = result.scalar_one_or_none()
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    return success_response(CompanyPublicRead.model_validate(company))
