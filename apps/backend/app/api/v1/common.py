"""Shared response helpers for v1 routers."""

from fastapi import Query
from pydantic import BaseModel


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


class Pagination:
    def __init__(
        self,
        limit: int = Query(default=25, ge=1, le=100),
        offset: int = Query(default=0, ge=0, le=100_000),
    ) -> None:
        self.limit = limit
        self.offset = offset


class Message(BaseModel):
    message: str
