"""Interface for database storage."""

__version__ = "0.0.9"

from . import models
from .database import Database

__all__ = ["Database", "models"]
