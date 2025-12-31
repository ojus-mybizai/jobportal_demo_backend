from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel
from pydantic.generics import GenericModel


T = TypeVar("T")


class APIError(BaseModel):
    code: str
    message: str
    details: Optional[dict[str, Any]] = None


class APIResponse(GenericModel, Generic[T]):
    status: str
    data: Optional[T] = None
    error: Optional[APIError] = None

    class Config:
        arbitrary_types_allowed = True


def success_response(data: Any) -> APIResponse[Any]:
    return APIResponse(status="success", data=data, error=None)


def error_response(code: str, message: str, details: dict[str, Any] | None = None) -> APIResponse[Any]:
    return APIResponse(status="error", data=None, error=APIError(code=code, message=message, details=details))
