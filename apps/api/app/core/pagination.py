"""Shared list pagination: `offset` (or its alias `skip`) + `limit`, with the full match count in X-Total-Count.

List bodies stay plain arrays so existing clients keep working; tables read the header to size their pagination.
"""

from typing import Annotated

from fastapi import Depends, Query, Response
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

TOTAL_COUNT_HEADER = "X-Total-Count"


def page_offset(
    offset: Annotated[int | None, Query(ge=0, description="Rows to skip.")] = None,
    skip: Annotated[int | None, Query(ge=0, description="Alias of `offset`.")] = None,
) -> int:
    if offset is not None:
        return offset
    return skip if skip is not None else 0


Offset = Annotated[int, Depends(page_offset)]


def set_total(response: Response, total: int) -> None:
    response.headers[TOTAL_COUNT_HEADER] = str(total)


def count_rows(db: Session, statement: Select) -> int:
    """Total rows `statement` matches, ignoring its ordering, offset and limit."""
    inner = statement.order_by(None).limit(None).offset(None)
    return int(db.scalar(select(func.count()).select_from(inner.subquery())) or 0)
