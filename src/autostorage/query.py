"""Convenient querying methods."""

from collections.abc import Iterator

from automatics import geom, model
from sqlmodel import Session

from . import select
from .base import BaseRowT
from .database import Database
from .models import GeometryRow, ModelRow


def first_match(db: Database, row: BaseRowT) -> BaseRowT | None:
    """Return matching row if found."""
    stmt = select.matching_rows(row)
    return db.exec_first(stmt)


def all_matches(db: Database, row: BaseRowT) -> Iterator[BaseRowT]:
    """Yield matching rows if found."""
    stmt = select.matching_rows(row)
    yield from db.exec_all(stmt)


def one_match(db: Database, row: BaseRowT) -> BaseRowT:
    """Return matching row if found."""
    stmt = select.matching_rows(row)
    return db.exec_one(stmt)


def geometry_match(sess: Session, geo: GeometryRow) -> GeometryRow | None:
    """Return matching geometry if found."""
    geo_hash = geo.hash or geom.geometry_hash(geo)
    geo_partial = GeometryRow.partial(hash=geo_hash)
    stmt = select.matching_rows(geo_partial)
    return sess.exec(stmt).one()


def model_match(db: Database, mod: ModelRow) -> ModelRow | None:
    """Return matching model if found."""
    model_hash = mod.hash or model.model_hash(mod)
    model_partial = ModelRow.partial(hash=model_hash)
    return first_match(db, model_partial)
