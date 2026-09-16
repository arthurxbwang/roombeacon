from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PageInfo(BaseModel):
    current_page: int
    page_size: int
    total: int


class R(BaseModel, Generic[T]):  # noqa: UP046 - preserve public Pydantic generic metadata in this cleanup
    """Unified API response wrapper."""
    code: int = 0
    message: str = "ok"
    data: T | None = None
    trace_id: str | None = None


class PagedR(BaseModel, Generic[T]):  # noqa: UP046 - preserve public Pydantic generic metadata in this cleanup
    code: int = 0
    message: str = "ok"
    data: list[T] = []
    page_info: PageInfo | None = None
    trace_id: str | None = None


def ok(data: Any = None, message: str = "ok") -> dict:
    return {"code": 0, "message": message, "data": data}


def fail(code: int = -1, message: str = "error", data: Any = None) -> dict:
    return {"code": code, "message": message, "data": data}


def paged(items: list, total: int, page: int, size: int) -> dict:
    return {
        "code": 0,
        "message": "ok",
        "data": items,
        "page_info": {"current_page": page, "page_size": size, "total": total},
    }
