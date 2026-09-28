"""Shared column types."""

from typing import Any

from sqlalchemy import JSON, Enum
from sqlalchemy.dialects.postgresql import JSONB

JSONType = JSON().with_variant(JSONB(), "postgresql")


def enum_column(enum: type[Any], name: str) -> Enum:
    """VARCHAR + CHECK constraint (no native PG enum), so adding values is a simple migration."""
    return Enum(
        enum,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda members: [m.value for m in members],
        validate_strings=True,
    )
