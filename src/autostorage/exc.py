"""Autostorage exceptions."""

from typing import Self

__all__ = ["DataIntegrityError", "ResultShapeError"]


class DataIntegrityError(Exception):
    """Raise when an ORM event detects a data integrity violation."""


class ResultShapeError(Exception):
    """Raise when a result violates expected shape."""

    def __init__(
        self: Self, model: object, actual: tuple[int, ...], expected: tuple[int, ...]
    ) -> None:
        """Initialize exception."""
        class_name = model.__class__.__name__
        msg = f"{class_name} shape ({actual}) does not match expected ({expected})."
        super().__init__(msg)
