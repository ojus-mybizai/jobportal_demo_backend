from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession


async def validate_master_active(
    session: AsyncSession,
    model,
    item_id: UUID | None,
    field_name: str,
) -> None:
    if item_id is None:
        return
    obj = await session.get(model, item_id)
    if not obj or not getattr(obj, "is_active", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid or inactive {field_name}",
        )
