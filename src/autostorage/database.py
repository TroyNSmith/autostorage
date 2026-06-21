"""Database connection."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import numpy as np
from automatics import Identity, model
from automol import geom
from sqlalchemy import event, insert
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.sql.expression import SelectOfScalar

from .models import (
    BaseRowT,
    CalculationRow,  # noqa: F401
    EnergyRow,
    GeometryRow,
    GradientRow,
    HessianRow,
    IdentityExtraRow,
    IdentityRow,
    ModelRow,
    StageRow,  # noqa: F401
    StationaryIdentityLink,  # noqa: F401
    StationaryPointRow,
    StationaryStageLink,  # noqa: F401
    StepRow,  # noqa: F401
    StepValidationLink,  # noqa: F401
    StepValidationRow,  # noqa: F401
    TrajectoryGeometryLink,  # noqa: F401
    TrajectoryRow,
)
from .utils.exc import (
    DatabaseValidationError,
    ImmutabilityViolationError,
    ShapeMismatchError,
)

__all__ = ["Database"]


class Database:
    """
    Database connection manager.

    Attributes
    ----------
    path
        Path to SQLite database file.
    engine
        SQLAlchemy engine instance.
    _session
        Persistent database session.
    """

    def __init__(self, path: str | Path, *, echo: bool = False) -> None:
        """
        Initialize database connection manager.

        Parameters
        ----------
        path
            Path to the SQLite database file.
        echo, optional
            If True, SQL statements will be logged to the standard output.
            If False, no logging is performed.
        """
        self.path = Path(path)
        self.engine = create_engine(f"sqlite:///{self.path}", echo=echo)
        SQLModel.metadata.create_all(self.engine)

        self._session: Session = Session(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Yield a persisted session."""
        yield self._session

    def add(self, row: BaseRowT) -> BaseRowT:
        """Update existing row or insert if not found."""
        with self.session() as session:
            try:
                session.add(row)
                session.commit()
                session.refresh(row)

            except Exception:
                session.rollback()
                raise

            return row

    def delete(self, row: BaseRowT) -> None:
        """Delete row from database."""
        with self.session() as session:
            session.delete(row)
            session.commit()

    def get(self, model: type[BaseRowT], row_id: int) -> BaseRowT:
        """Get row from database."""
        with self.session() as session:
            row = session.get(model, row_id)
            if row is not None:
                return row

        msg = f"{model} with {row_id = } not found."
        raise LookupError(msg)

    def exec_first(self, stmt: SelectOfScalar[BaseRowT]) -> BaseRowT | None:
        """Return the first match to a statement."""
        with self.session() as sess:
            return sess.exec(stmt).first()

    def exec_one(self, stmt: SelectOfScalar[BaseRowT]) -> BaseRowT:
        """Return the first match to a statement."""
        with self.session() as sess:
            return sess.exec(stmt).one()

    def exec_all(self, stmt: SelectOfScalar[BaseRowT]) -> Iterator[BaseRowT]:
        """Yield all matches to a statement."""
        with self.session() as sess:
            yield from sess.exec(stmt).all()

    def close(self) -> None:
        """Close the database connection."""
        self.engine.dispose()


@event.listens_for(ModelRow, "before_insert")
def ensure_model_hash(mapper, connection, target: ModelRow) -> None:  # noqa: ANN001, ARG001
    """Compute and assign the model hash before inserting a ModelRow."""
    if target is not None and target.hash is None:
        target.hash = model.model_hash(target)


@event.listens_for(GeometryRow, "before_insert")
@event.listens_for(GeometryRow, "before_update")
def ensure_geometry_hash(mapper, connection, target: GeometryRow) -> None:  # noqa: ANN001, ARG001
    """Compute and assign the geometry hash before inserting a GeometryRow."""
    if target.hash is None:
        target.hash = geom.geometry_hash(target)


@event.listens_for(GradientRow, "before_insert")
@event.listens_for(GradientRow, "before_update")
def verify_gradient_shape(mapper, connection, target: GradientRow) -> None:  # noqa: ANN001, ARG001
    """Verify shape of the gradient array before saving to DB."""
    if not target.geometry:
        return

    exp_shape = (3 * target.geometry.atom_count,)
    val_shape = np.shape(target.value)

    if val_shape != exp_shape:
        msg = f"Expected {exp_shape} gradient, got {val_shape}."
        raise ShapeMismatchError(msg)


@event.listens_for(HessianRow, "before_insert")
@event.listens_for(HessianRow, "before_update")
def verify_hessian_shape(mapper, connection, target: HessianRow) -> None:  # noqa: ANN001, ARG001
    """Verify shape of the Hessian matrix before saving to DB."""
    if not target.geometry:
        return

    exp_shape = (3 * target.geometry.atom_count, 3 * target.geometry.atom_count)
    val_shape = np.shape(target.value)

    if val_shape != exp_shape:
        msg = f"Expected {exp_shape} Hessian, got {val_shape}."
        raise ShapeMismatchError(msg)


@event.listens_for(EnergyRow, "before_update")
@event.listens_for(GradientRow, "before_update")
@event.listens_for(HessianRow, "before_update")
def enforce_immutable_results(mapper, connection, target) -> None:  # noqa: ANN001, ARG001
    """Enforce immutable results after insert."""
    msg = f"Modifications to {target.__class__.__name__} are forbidden."
    raise ImmutabilityViolationError(msg)


@event.listens_for(Session, "before_flush")
def add_inchi_identities(session, flush_context, instances) -> None:  # noqa: ANN001, ARG001
    """Attach InChI and SMILES identities to new stationary point rows before flush."""
    for obj in session.new:
        if not isinstance(obj, StationaryPointRow):
            continue
        try:
            inchi_row = IdentityRow.from_geometry(
                geo=obj.geometry,
                algorithm="rdkit inchi",
            )
        except ValueError:
            # NOTE: Add logger
            continue

        existing = session.exec(
            select(IdentityRow).where(
                IdentityRow.algorithm == inchi_row.algorithm,
                IdentityRow.value == inchi_row.value,
            )
        ).first()

        if existing is None:
            smiles = Identity.from_geometry(
                obj.geometry,
                algorithm="rdkit smiles",
            )

            inchi_row.identity_extras.append(
                IdentityExtraRow(
                    attribute="smiles",
                    value=smiles.value,
                )
            )

            session.add(inchi_row)
            existing = inchi_row

        obj.identities.append(existing)


@event.listens_for(StationaryPointRow, "before_insert")
@event.listens_for(StationaryPointRow, "before_update")
def validate_stationary_order(mapper, connection, target: StationaryPointRow) -> None:  # noqa: ANN001
    """Compute hessian frequencies and verify stationary point order before insert."""
    hessians = target.hessians

    if not hessians:
        if target.is_valid:
            msg = "StationaryPoint cannot be valid without an associated Hessian."
            raise DatabaseValidationError(msg)
        return

    orders = set()
    for hess in hessians:
        freq, _ = geom.vibrational_analysis(target.geometry, hess.value)
        orders.add(sum(1 for f in freq if f < 0))

    if len(orders) > 1:
        msg = (
            f"Hessians for {target.geometry_id} disagree on stationary order:"
            f"{sorted(orders)}"
        )
        raise DatabaseValidationError(msg)

    hess_order = orders.pop()

    if target.order != hess_order:
        target.is_valid = False

        stmt = insert(mapper.local_table).values(
            geometry_id=target.geometry_id,
            calculation_id=target.calculation_id,
            order=hess_order,
            is_pseudo=target.is_pseudo,
            is_valid=True,
        )

        connection.execute(stmt)

    else:
        target.is_valid = True


@event.listens_for(TrajectoryRow, "before_insert")
@event.listens_for(TrajectoryRow, "before_update")
def indices_match_len(mapper, connection, target: TrajectoryRow) -> None:  # noqa: ANN001, ARG001
    """Verify trajectory indices match length of trajectory."""
    has_index = [s.index is not None for s in target.steps]
    if any(has_index) and not all(has_index):
        msg = "Either all or none of the trajectory steps must have an index."
        raise ValueError(msg)
    if target.indices and len(target.indices) != len(target.geometries):
        msg = "Number of indices does not match number of geometries."
        raise ValueError(msg)
