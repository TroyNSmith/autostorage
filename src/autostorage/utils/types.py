"""Autostorage types."""

import numpy as np
from sqlalchemy import JSON, TypeDecorator


class FloatArrayTypeDecorator(TypeDecorator):
    """SQLAlchemy NDArray -> JSON type decorator."""

    impl = JSON
    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: ANN001, ANN201, ARG002
        """Convert NumPy array to list for database."""
        if value is None:
            return None
        if isinstance(value, np.ndarray):
            return value.tolist()
        return value

    def process_result_value(self, value, dialect):  # noqa: ANN001, ANN201, ARG002
        """Convert list from database back to NumPy array."""
        if value is None:
            return None
        return np.array(value, dtype=float)
