"""Base row/link classes shared across all row modules."""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Self, dataclass_transform

from sqlalchemy import inspect as sa_inspect
from sqlmodel import Field, SQLModel, func, select

from autostorage.exc import MissingPrimaryKeyError

if TYPE_CHECKING:
    from autostorage.database import Database

    from .calc import ModelRow
    from .geom import GeometryRow


def _fk_field(target: str, *, nullable: bool = False, index: bool = True) -> Any:  # noqa: ANN401
    """Build a standard foreign-key Field with ON DELETE CASCADE."""
    return Field(
        default=None,
        foreign_key=target,
        ondelete="CASCADE",
        nullable=nullable,
        index=index,
    )


@dataclass_transform(kw_only_default=True, field_specifiers=(Field,))
class TimestampMixin(SQLModel):
    """Mixin adding server-managed creation/update timestamps.

    Annotated as `datetime | None` since the value is unset in Python until the
    database fills it in via `server_default`/`onupdate`; `nullable=False`
    overrides the `NULL`-by-default column that an Optional annotation would
    otherwise produce, since the DB always has a value once the row is flushed.
    """

    created_at: datetime | None = Field(
        default=None,
        nullable=False,
        sa_column_kwargs={"server_default": func.now()},
    )
    updated_at: datetime | None = Field(
        default=None,
        nullable=False,
        sa_column_kwargs={"server_default": func.now(), "onupdate": func.now()},
    )


@dataclass_transform(kw_only_default=True, field_specifiers=(Field,))
class BaseRow(TimestampMixin, SQLModel):
    """Base for models with a primary ID."""

    id: int | None = Field(default=None, primary_key=True)


class BaseResultRow(BaseRow):
    """Base for result models."""

    geometry_id: int | None

    @classmethod
    def query(
        cls,
        db: "Database",
        *,
        geo: "GeometryRow",
        model: "ModelRow",
        prov: dict[str, Any] | None = None,
    ) -> Self | None:
        """Query for result matching geometry, model, and provenance."""
        from .calc import CalculationRow  # noqa: PLC0415

        if not geo.id or not model.id:
            raise MissingPrimaryKeyError([geo, model])

        prov = prov or {}
        stmt = (
            select(cls)
            .join(CalculationRow)
            .where(
                cls.geometry_id == geo.id,
                CalculationRow.model_id == model.id,
                CalculationRow.input_provenance == prov,
            )
        )
        return db.exec_first(stmt)


@dataclass_transform(kw_only_default=True, field_specifiers=(Field,))
class BaseLink(SQLModel):
    """Base for models without a primary ID."""

    @classmethod
    def create(cls, *rows: BaseRow, **attrs: object) -> Self:
        """Construct a link, matching each row to its relationship by type.

        Parameters
        ----------
        *rows
            The rows to link (e.g. a ``GeometryRow`` and a ``CalculationRow``),
            in any order.
        **attrs
            Extra attributes to set on the link (e.g. ``role``).

        Returns
        -------
        Self
            The constructed (unsaved) link row.
        """
        relationships = sa_inspect(cls, raiseerr=True).relationships
        fields: dict[str, BaseRow] = {}
        for row in rows:
            matches = [
                rel.key
                for rel in relationships
                if rel.key not in fields and isinstance(row, rel.mapper.class_)
            ]
            if not matches:
                msg = f"{cls.__name__} has no unmatched relationship for {row!r}."
                raise ValueError(msg)
            if len(matches) > 1:
                # Ambiguous: two+ unfilled relationships share this row's type,
                # so matching by type alone can't tell them apart (e.g. a link
                # table with two relationships to the same row model). Raise
                # rather than silently picking one by declaration order.
                msg = (
                    f"{cls.__name__} has multiple unmatched relationships "
                    f"{matches} for {row!r}; construct this link directly instead."
                )
                raise ValueError(msg)
            fields[matches[0]] = row
        return cls(**fields, **attrs)
