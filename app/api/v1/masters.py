import uuid
from typing import Dict, List, Optional, Type
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.response import APIResponse, error_response, success_response
from app.models.master import (
    MasterCompanyCategory,
    MasterLocation,
    MasterJobCategory,
    MasterExperienceLevel,
    MasterSkill,
    MasterEducation,
    MasterDegree,
)
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.master import MasterCreate, MasterRead, MasterUpdate


router = APIRouter(prefix="/masters", tags=["masters"])


MASTER_MODEL_MAP: Dict[str, Type] = {
    "company_category": MasterCompanyCategory,
    "location": MasterLocation,
    "job_category": MasterJobCategory,
    "experience_level": MasterExperienceLevel,
    "skill": MasterSkill,
    "education": MasterEducation,
    "degree": MasterDegree,
}


@router.get("", response_model=APIResponse[List[str]])
async def list_master_types(
    current_user: User = Depends(deps.get_current_active_user),
) -> APIResponse[List[str]]:
    return success_response(sorted(MASTER_MODEL_MAP.keys()))


def get_master_model(master_name: str) -> Type:
    model = MASTER_MODEL_MAP.get(master_name)
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown master '{master_name}'",
        )
    return model


@router.get("/{master_name}", response_model=APIResponse[PaginatedResponse[MasterRead]])
async def list_masters(
    master_name: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    q: Optional[str] = Query(None, description="Search by name"),
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user),
) -> APIResponse[PaginatedResponse[MasterRead]]:
    model = get_master_model(master_name)

    stmt = select(model)
    total_stmt = select(func.count()).select_from(model)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(model.name.ilike(like))
        total_stmt = total_stmt.where(model.name.ilike(like))

    stmt = stmt.limit(limit).offset((page - 1) * limit)

    result = await session.execute(stmt)
    items = [MasterRead.model_validate(obj) for obj in result.scalars().all()]

    total_result = await session.execute(total_stmt)
    total = total_result.scalar_one() or 0

    data = PaginatedResponse[MasterRead](items=items, total=total, page=page, limit=limit)
    return success_response(data)


@router.post("/{master_name}", response_model=APIResponse[MasterRead])
async def create_master(
    master_name: str,
    body: MasterCreate,
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin"])),
) -> APIResponse[MasterRead]:
    model = get_master_model(master_name)

    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="name is required")

    new_id = uuid.uuid4()
    insert_stmt = (
        insert(model.__table__)
        .values(id=new_id, name=name)
        .on_conflict_do_nothing()
        .returning(model.__table__.c.id)
    )
    try:
        inserted_id = (await session.execute(insert_stmt)).scalar_one_or_none()
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        orig = getattr(exc, "orig", None)
        orig_class = getattr(orig, "__class__", None)
        orig_name = getattr(orig_class, "__name__", None)
        orig_detail = getattr(orig, "detail", None)
        orig_constraint = getattr(orig, "constraint_name", None)
        db_error = str(orig) if orig is not None else str(exc)

        is_unique_violation = (orig_name == "UniqueViolationError") or ("unique" in db_error.lower())
        message = "Master value already exists" if is_unique_violation else "Master value integrity error"

        if is_unique_violation:
            conflict_stmt = select(model).where(func.lower(func.btrim(model.name)) == name.lower())
            conflict_res = await session.execute(conflict_stmt)
            conflict = conflict_res.scalar_one_or_none()
            if conflict is not None:
                return success_response(MasterRead.model_validate(conflict))

        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=error_response(
                code="conflict",
                message=message,
                details={
                    "master": master_name,
                    "name": name,
                    "db_error_type": orig_name,
                    "db_error_detail": orig_detail,
                    "db_constraint": orig_constraint,
                    "db_error": db_error,
                },
            ).model_dump(),
        )

    if inserted_id is not None:
        obj = await session.get(model, inserted_id)
        return success_response(MasterRead.model_validate(obj))

    existing_stmt = select(model).where(func.lower(func.btrim(model.name)) == name.lower())
    existing_res = await session.execute(existing_stmt)
    existing = existing_res.scalar_one_or_none()
    if existing is not None:
        return success_response(MasterRead.model_validate(existing))

    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=error_response(
            code="conflict",
            message="Master value already exists",
            details={"master": master_name, "name": name},
        ).model_dump(),
    )


@router.put("/{master_name}/{item_id}", response_model=APIResponse[MasterRead])
async def update_master(
    master_name: str,
    item_id: UUID,
    body: MasterUpdate,
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin"])),
) -> APIResponse[MasterRead]:
    model = get_master_model(master_name)
    obj = await session.get(model, item_id)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Master not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(obj, field, value)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        orig = getattr(exc, "orig", None)
        orig_class = getattr(orig, "__class__", None)
        orig_name = getattr(orig_class, "__name__", None)
        orig_detail = getattr(orig, "detail", None)
        orig_constraint = getattr(orig, "constraint_name", None)
        db_error = str(orig) if orig is not None else str(exc)

        conflict_name = body.name.strip() if body.name else None
        if conflict_name:
            conflict_stmt = select(model).where(
                and_(
                    func.lower(func.btrim(model.name)) == conflict_name.lower(),
                    model.id != item_id,
                )
            )
            conflict_res = await session.execute(conflict_stmt)
            conflict = conflict_res.scalar_one_or_none()
            if conflict is not None:
                return JSONResponse(
                    status_code=status.HTTP_409_CONFLICT,
                    content=error_response(
                        code="conflict",
                        message="Master value conflict",
                        details={
                            "master": master_name,
                            "item_id": str(item_id),
                            "name": conflict_name,
                            "existing_id": str(conflict.id),
                        },
                    ).model_dump(),
                )

        is_unique_violation = (orig_name == "UniqueViolationError") or ("unique" in db_error.lower())
        message = "Master value conflict" if is_unique_violation else "Master value integrity error"

        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=error_response(
                code="conflict",
                message=message,
                details={
                    "master": master_name,
                    "item_id": str(item_id),
                    "db_error_type": orig_name,
                    "db_error_detail": orig_detail,
                    "db_constraint": orig_constraint,
                    "db_error": db_error,
                },
            ).model_dump(),
        )
    await session.refresh(obj)
    return success_response(MasterRead.model_validate(obj))


@router.delete("/{master_name}/{item_id}", response_model=APIResponse[MasterRead])
async def delete_master(
    master_name: str,
    item_id: UUID,
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.require_role(["admin"])),
) -> APIResponse[MasterRead]:
    model = get_master_model(master_name)
    obj = await session.get(model, item_id)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Master not found")

    await session.delete(obj)
    await session.commit()
    return success_response(MasterRead.model_validate(obj))
