import os
import uuid
from pathlib import Path
from typing import Optional

import boto3
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.file import File
from app.models.user import User


class FileService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.media_root = Path(settings.MEDIA_ROOT)
        self.media_root.mkdir(parents=True, exist_ok=True)
        self.use_s3 = settings.USE_S3_STORAGE

        if self.use_s3:
            s3_kwargs: dict = {
                "region_name": settings.AWS_REGION,
                "endpoint_url": settings.AWS_S3_ENDPOINT_URL or None,
            }
            if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
                s3_kwargs.update(
                    {
                        "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
                        "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
                    }
                )

            self.s3_client = boto3.client("s3", **s3_kwargs)

            if not settings.AWS_S3_BASE_URL:
                # Fallback to standard S3 URL if base not provided
                base = f"https://{settings.AWS_S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com"
                object.__setattr__(settings, "AWS_S3_BASE_URL", base)  # type: ignore

            print("boto client successfull" , self.s3_client)
        else:
            print("no client connection error")
            self.s3_client = None

    async def save_upload(self, upload: UploadFile, uploaded_by: Optional[User]) -> File:
        ext = os.path.splitext(upload.filename or "")[1]
        generated_name = f"{uuid.uuid4()}{ext}"
        content = await upload.read()

        if self.use_s3 and self.s3_client:
            key = f"{settings.AWS_S3_FOLDER_PREFIX}{generated_name}"
            extra_args = {"ContentType": upload.content_type or "application/octet-stream"}
            if settings.AWS_S3_PUBLIC_READ:
                extra_args["ACL"] = "public-read"

            self.s3_client.put_object(
                Bucket=settings.AWS_S3_BUCKET,
                Key=key,
                Body=content,
                **extra_args,
            )
            public_url = f"{settings.AWS_S3_BASE_URL}/{key}"
        else:
            target_path = self.media_root / generated_name
            with open(target_path, "wb") as f:
                f.write(content)
            public_url = f"/media/{generated_name}"

        db_file = File(
            url=public_url,
            filename=upload.filename or generated_name,
            mimetype=upload.content_type,
            size=len(content),
            uploaded_by=uploaded_by.id if uploaded_by else None,
        )
        self.session.add(db_file)
        await self.session.commit()
        await self.session.refresh(db_file)
        return db_file

    async def get_file(self, file_id) -> Optional[File]:
        result = await self.session.get(File, file_id)
        return result
