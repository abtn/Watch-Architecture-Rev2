"""A small SQLAlchemy type adapter for PostgreSQL's pgvector VECTOR type.

The project deliberately avoids a runtime dependency on the pgvector Python
package. PostgreSQL still supplies the vector operators and storage type.
"""

import math
from collections.abc import Callable, Sequence
from typing import Any

from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import UserDefinedType


def validate_vector(
    values: Sequence[object], dimensions: int | None = None
) -> list[float]:
    """Return a finite float vector, rejecting malformed shapes and values."""
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError("invalid_embedding_vector")
    if dimensions is not None and len(values) != dimensions:
        raise ValueError("embedding_dimension_mismatch")
    if not values:
        raise ValueError("empty_embedding_vector")

    vector: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("non_numeric_embedding_value")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("non_finite_embedding_value")
        vector.append(number)
    return vector


def serialize_vector(values: Sequence[object]) -> str:
    """Serialize a finite vector using pgvector's text input format."""
    vector = validate_vector(values)
    return "[" + ",".join(format(value, ".17g") for value in vector) + "]"


def parse_vector(value: Any) -> list[float] | None:
    """Parse a PostgreSQL vector value returned as text or a numeric sequence."""
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text.startswith("[") or not text.endswith("]"):
            raise ValueError("invalid_database_vector")
        contents = text[1:-1].strip()
        if not contents:
            raise ValueError("empty_database_vector")
        try:
            values: Sequence[object] = [
                float(part.strip()) for part in contents.split(",")
            ]
        except ValueError as error:
            raise ValueError("invalid_database_vector") from error
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        values = value
    else:
        raise ValueError("invalid_database_vector")
    return validate_vector(values)


class Vector(UserDefinedType[list[float]]):
    """PostgreSQL VECTOR type without binding dimensions into the column type."""

    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:
        return "VECTOR"

    def bind_processor(
        self, dialect: Dialect
    ) -> Callable[[Any], Any] | None:
        def process(value: Any) -> str | None:
            if value is None:
                return None
            return serialize_vector(value)

        return process

    def result_processor(
        self, dialect: Dialect, coltype: Any
    ) -> Callable[[Any], Any] | None:
        return parse_vector
