from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.config import settings
from app.core.response import APIResponse, success_response
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.crud.user import authenticate_user, create_user, get_user_by_email, get_user_by_id
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenData, RefreshRequest
from app.schemas.user import UserCreate, UserRead


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=APIResponse[TokenData])
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(deps.get_db_session),
) -> APIResponse[TokenData]:
    user = await authenticate_user(session, body.email, body.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect email or password")

    access_token_expires = settings.ACCESS_TOKEN_EXPIRE_MINUTES
    refresh_token_expires = settings.REFRESH_TOKEN_EXPIRE_MINUTES
    access_token = create_access_token(str(user.id), expires_minutes=access_token_expires)
    refresh_token = create_refresh_token(str(user.id), expires_minutes=refresh_token_expires)
    token_data = TokenData(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=access_token_expires,
        refresh_expires_in=refresh_token_expires,
    )
    return success_response(token_data)


@router.post("/register", response_model=APIResponse[UserRead])
async def register_user(
    user_in: UserCreate,
    current_user: User = Depends(deps.require_role(["admin"])),
    session: AsyncSession = Depends(deps.get_db_session),
) -> APIResponse[UserRead]:
    existing = await get_user_by_email(session, user_in.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    user = await create_user(session, user_in)
    return success_response(UserRead.model_validate(user))


@router.get("/me", response_model=APIResponse[UserRead])
async def read_users_me(
    current_user: User = Depends(deps.get_current_active_user),
) -> APIResponse[UserRead]:
    return success_response(UserRead.model_validate(current_user))


@router.post("/refresh", response_model=APIResponse[TokenData])
async def refresh_token(body: RefreshRequest) -> APIResponse[TokenData]:
    try:
        payload = decode_token(body.refresh_token)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    token_type = payload.get("type")
    if user_id is None or token_type != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Load user to ensure still valid/active
    async for session in deps.get_db():
        user = await get_user_by_id(session, user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        access_token_expires = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        refresh_token_expires = settings.REFRESH_TOKEN_EXPIRE_MINUTES
        new_access = create_access_token(str(user.id), expires_minutes=access_token_expires)
        new_refresh = create_refresh_token(str(user.id), expires_minutes=refresh_token_expires)
        token_data = TokenData(
            access_token=new_access,
            refresh_token=new_refresh,
            expires_in=access_token_expires,
            refresh_expires_in=refresh_token_expires,
        )
        return success_response(token_data)
