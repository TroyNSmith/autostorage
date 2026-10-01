"""SQLite database connection management."""

import json
from functools import partial
from pathlib import Path
from types import TracebackType
from typing import Self

from sqlalchemy import URL, create_engine, event
from sqlmodel import SQLModel

# Ensure all modules are loaded with the database
from . import events
from .models import *  # noqa: F403

__all__ = ["Database"]


class Database:
    """Database connection manager.

    Attributes:
        path: Path to SQLite database file.
        engine: SQLAlchemy engine instance.
    """

    def __init__(self, path: str | Path, *, echo: bool = False) -> None:
        """Initialize database connection manager.

        Args:
            path: Path to the SQLite database file.
            echo: If True, SQL statements will be logged to the standard output.
                If False, no logging is performed.
        """
        self.path = Path(path)
        self.engine = create_engine(
            URL.create("sqlite", database=str(self.path)),
            echo=echo,
            # Canonicalize dict key order so JSON-column equality filters (e.g.
            # `CalculationRow.input_provenance == prov`) match regardless of the
            # key insertion order used to build the Python dict being compared.
            json_serializer=partial(json.dumps, sort_keys=True),
            # Allow multithreading
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(self.engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
            """Set SQLite pragmas."""
            cursor = dbapi_connection.cursor()
            # SQLite ignores FK constraints unless enabled
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        SQLModel.metadata.create_all(self.engine)
        with self.session() as seed_session:
            events.create_identity_algorithms(seed_session)
            events.create_property_kinds(seed_session)

    def session(self) -> events.AutostorageSession:
        """Return a fresh session bound to this database's engine.

        Note:
            A new session is created per call; use it as a context manager
            (`with database.session() as session: ...`) to close it on exit.
            Nothing is committed automatically — call `session.commit()` explicitly.
            Validation and automatic identities are only applied by sessions of
            type `AutostorageSession`, such as the ones returned here.
        """
        return events.AutostorageSession(self.engine)

    def close(self) -> None:
        """Close the database connection."""
        self.engine.dispose()

    def __enter__(self) -> Self:
        """Return this database, to be closed on exiting the context."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the database connection."""
        self.close()
