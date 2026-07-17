"""
Shared response envelope schemas.

EVERY successful API response is wrapped as:
    {"success": true, "data": <payload>, "meta": <pagination|null>}
and every error as (see core/exceptions.py):
    {"success": false, "error": {"code", "message", "details"}}

One envelope = the frontend writes exactly one response interceptor.
`APIResponse` is generic, so OpenAPI docs still show the precise payload
type for each endpoint (e.g. APIResponse[MeetingDetail]).
"""

from pydantic import BaseModel, Field


class PaginationMeta(BaseModel):
    """Standard pagination block for list endpoints."""

    page: int = Field(ge=1, description="Current page number (1-based)")
    page_size: int = Field(ge=1, le=100, description="Items per page")
    total_items: int = Field(ge=0, description="Total items matching the query")
    total_pages: int = Field(ge=0, description="Total number of pages")

    @classmethod
    def build(cls, *, page: int, page_size: int, total_items: int) -> "PaginationMeta":
        """Compute total_pages once, here, instead of in every service."""
        total_pages = (total_items + page_size - 1) // page_size if total_items else 0
        return cls(page=page, page_size=page_size, total_items=total_items, total_pages=total_pages)


class APIResponse[T](BaseModel):  # PEP 695 generics (Python 3.12+)
    """Success envelope. `meta` is only populated by paginated endpoints."""

    success: bool = True
    data: T | None = None
    meta: PaginationMeta | None = None


class ErrorDetail(BaseModel):
    """Machine-readable error description (mirrors core/exceptions.py)."""

    code: str
    message: str
    details: object | None = None


class APIErrorResponse(BaseModel):
    """Error envelope — referenced in OpenAPI docs for error responses."""

    success: bool = False
    error: ErrorDetail
