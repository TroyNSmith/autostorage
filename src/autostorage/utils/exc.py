"""Autostorage exceptions."""


class ShapeMismatchError(Exception):
    """Raise an error when results do not match expected shape."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class ImmutabilityViolationError(Exception):
    """Raise an error when attempting to update existing results."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class DatabaseValidationError(Exception):
    """Raise an error when attempting to validate database rows."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
