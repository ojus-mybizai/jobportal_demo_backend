from uuid import UUID

from fastapi import APIRouter, Depends, File as FastAPIFile, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.response import APIResponse, success_response
from app.models.file import File
from app.models.user import User
from app.schemas.file import FileRead
from app.services.file_service import FileService


router = APIRouter(prefix="/files", tags=["files"])


@router.post("/upload", response_model=APIResponse[FileRead])
async def upload_file(
    file: UploadFile = FastAPIFile(...),
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user),
) -> APIResponse[FileRead]:
    file_service = FileService(session)
    stored = await file_service.save_upload(file, current_user)
    return success_response(FileRead.model_validate(stored))


@router.get("/{file_id}", response_model=APIResponse[dict])
async def get_file_presigned_url(
    file_id: UUID,
    session: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user),
) -> APIResponse[dict]:
    stored = await session.get(File, file_id)
    if not stored or not stored.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    # In a real S3 setup this would return a presigned URL.
    presigned_url = stored.url
    data = {
        "id": str(stored.id),
        "url": stored.url,
        "presigned_url": presigned_url,
    }
    return success_response(data)
