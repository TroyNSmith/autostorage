"""SQLAlchemy ORM event listeners for validation and auto-managed identities."""

from dataclasses import dataclass
from typing import Any

from automol import Algorithm
from automol.ident import AlgorithmRegistry
from sqlalchemy import event
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapper, Session
from sqlmodel import col, select

from .models import (
    GeometryRow,
    GeometryTrajectoryLink,
    GradientRow,
    HessianRow,
    IdentityAlgorithmRow,
    IdentityExtraRow,
    IdentityRow,
    IdentityStationaryLink,
    StationaryPointRow,
    StepRow,
)


def create_identity_algorithms(session: Session) -> None:
    """Create all identity algorithms in the database if they do not already exist."""
    logged: dict[str, IdentityAlgorithmRow] = {}

    def _add_algorithm(alg: Algorithm) -> IdentityAlgorithmRow:
        """Add an algorithm to the database if it does not already exist."""
        if alg.name in logged:
            return logged[alg.name]

        parent_id = None
        if alg.parent_algorithm is not None:
            parent = _add_algorithm(alg.parent_algorithm)
            parent_id = parent.id

        existing = session.query(IdentityAlgorithmRow).filter_by(name=alg.name).first()
        if existing is None:
            existing = IdentityAlgorithmRow(
                name=alg.name,
                kind=alg.kind,
                parent_algorithm_id=parent_id,
                deterministic=alg.deterministic,
            )
            session.add(existing)
            session.commit()

        logged[alg.name] = existing

        return existing

    for alg in AlgorithmRegistry.algorithms:
        _add_algorithm(alg)


@event.listens_for(StepRow, "before_insert")
@event.listens_for(StepRow, "before_update")
def sort_step_stage_ids(
    mapper: Mapper[StepRow],  # noqa: ARG001
    connection: Connection,  # noqa: ARG001
    target: StepRow,
) -> None:
    """Auto-sort stage_id1 and stage_id2 so stage_id1 < stage_id2."""
    if (
        target.stage_id1 is not None
        and target.stage_id2 is not None
        and target.stage_id1 > target.stage_id2
    ):
        target.stage_id1, target.stage_id2 = target.stage_id2, target.stage_id1


@event.listens_for(StepRow, "before_insert")
@event.listens_for(StepRow, "before_update")
def verify_step_barrierless_consistency(
    mapper: Mapper[StepRow],  # noqa: ARG001
    connection: Connection,  # noqa: ARG001
    target: StepRow,
) -> None:
    """Verify is_barrierless consistency with stage_id_ts."""
    if target.stage_id_ts is None:
        if not target.is_barrierless:
            msg = "Barrierless step (stage_id_ts=None) must have is_barrierless=True"
            raise ValueError(msg)
    elif target.is_barrierless:
        msg = (
            "Step with transition state (stage_id_ts!=None) must have "
            "is_barrierless=False"
        )
        raise ValueError(msg)


@event.listens_for(Session, "before_flush")
def verify_gradient_shapes_before_flush(
    session: Session,
    flush_context: Any,  # noqa: ARG001, ANN401
    instances: Any,  # noqa: ARG001, ANN401
) -> None:
    """Verify gradient shapes match 3 * natoms for all gradients being flushed."""
    for obj in list(session.new) + list(session.dirty):
        if not isinstance(obj, GradientRow):
            continue

        if obj.geometry_id is None:
            continue

        # Load the geometry to get natoms
        geometry_row = session.get(GeometryRow, obj.geometry_id)
        if geometry_row is None:
            continue

        natoms = len(geometry_row.symbols)
        expected_shape = (3 * natoms,)
        actual_shape = obj.value.shape

        if actual_shape != expected_shape:
            msg = (
                f"Gradient shape {actual_shape} does not match expected "
                f"shape {expected_shape} for geometry with {natoms} atoms"
            )
            raise ValueError(msg)


@event.listens_for(Session, "before_flush")
def verify_hessian_shapes_before_flush(
    session: Session,
    flush_context: Any,  # noqa: ARG001, ANN401
    instances: Any,  # noqa: ARG001, ANN401
) -> None:
    """Verify Hessian shapes match (3 * natoms, 3 * natoms) for all Hessians."""
    for obj in list(session.new) + list(session.dirty):
        if not isinstance(obj, HessianRow):
            continue

        if obj.geometry_id is None:
            continue

        # Load the geometry to get natoms
        geometry_row = session.get(GeometryRow, obj.geometry_id)
        if geometry_row is None:
            continue

        natoms = len(geometry_row.symbols)
        expected_shape = (3 * natoms, 3 * natoms)
        actual_shape = obj.value.shape

        if actual_shape != expected_shape:
            msg = (
                f"Hessian shape {actual_shape} does not match expected "
                f"shape {expected_shape} for geometry with {natoms} atoms"
            )
            raise ValueError(msg)


@event.listens_for(Session, "before_flush")
def verify_valid_stationary_has_hessian(
    session: Session,
    flush_context: Any,  # noqa: ARG001, ANN401
    instances: Any,  # noqa: ARG001, ANN401
) -> None:
    """Verify that stationary points marked as valid have an associated Hessian."""
    for obj in list(session.new) + list(session.dirty):
        if not isinstance(obj, StationaryPointRow):
            continue

        if not obj.is_validated:
            continue

        if obj.geometry_id is None:
            continue

        # Load the geometry to check for hessians
        geometry_row = session.get(GeometryRow, obj.geometry_id)
        if geometry_row is None:
            continue

        if not geometry_row.hessians:
            msg = (
                f"StationaryPointRow cannot be marked as valid without a Hessian "
                f"attached to its geometry (geometry_id={obj.geometry_id})"
            )
            raise ValueError(msg)


@event.listens_for(GeometryTrajectoryLink, "before_insert")
@event.listens_for(GeometryTrajectoryLink, "before_update")
def verify_trajectory_geometry_ndim_insert(
    mapper: Mapper[GeometryTrajectoryLink],  # noqa: ARG001
    connection: Connection,  # noqa: ARG001
    target: GeometryTrajectoryLink,
) -> None:
    """Ensure linked geometry's index length matches trajectory ndim."""
    if target.trajectory is None:
        return

    traj_ndim = target.trajectory.ndim
    index_len = len(target.index) if target.index is not None else None

    if index_len is not None and traj_ndim is not None and index_len != traj_ndim:
        msg = (
            f"Geometry index length {index_len} does not match "
            f"trajectory ndim {traj_ndim}"
        )
        raise ValueError(msg)

    if traj_ndim is None and index_len is not None:
        target.trajectory.ndim = index_len
    elif index_len is None and traj_ndim is not None:
        msg = f"Geometry index is missing but trajectory ndim is {traj_ndim}"
        raise ValueError(msg)


_IdentityCache = dict[tuple[int, str], IdentityRow]
_IdentityExtraCache = dict[tuple[int, str], IdentityExtraRow]


@dataclass
class _IdentityFlushContext:
    """Per-flush state shared by the identity-resolution helpers below."""

    session: Session
    cache: _IdentityCache
    extra_cache: _IdentityExtraCache


def _require_algorithm_id(algorithm_row: IdentityAlgorithmRow) -> int:
    """Return the primary key of an already-persisted algorithm row."""
    if algorithm_row.id is None:
        msg = f"IdentityAlgorithmRow {algorithm_row.name!r} is missing its primary key"
        raise ValueError(msg)
    return algorithm_row.id


def _get_or_create_identity(
    ctx: _IdentityFlushContext, algorithm_id: int, value: str
) -> IdentityRow:
    """Look up a pending or persisted identity, creating one if none exists."""
    key = (algorithm_id, value)
    ident = ctx.cache.get(key)
    if ident is None:
        ident = (
            ctx.session.query(IdentityRow)
            .filter(
                col(IdentityRow.algorithm_id) == algorithm_id,
                col(IdentityRow.value) == value,
            )
            .one_or_none()
        )
    if ident is None:
        ident = IdentityRow(algorithm_id=algorithm_id, value=value)
        ctx.session.add(ident)
    ctx.cache[key] = ident
    return ident


def _resolve_parent_identity(
    ctx: _IdentityFlushContext,
    obj: StationaryPointRow,
    algorithm: Algorithm,
    geo_row: GeometryRow,
) -> tuple[IdentityRow | None, dict[str, Any] | None]:
    """Resolve the parent identity and sibling geometries for `algorithm`."""
    if algorithm.parent_algorithm is None:
        return None, None

    parent_alg = (
        ctx.session.query(IdentityAlgorithmRow)
        .filter(col(IdentityAlgorithmRow.name) == algorithm.parent_algorithm.name)
        .one()
    )
    parent_alg_id = _require_algorithm_id(parent_alg)
    parent_val = algorithm.parent_algorithm.identity_fn(geo_row)
    is_new_parent = (parent_alg_id, parent_val) not in ctx.cache
    parent_ident = _get_or_create_identity(ctx, parent_alg_id, parent_val)

    if is_new_parent:
        if parent_ident not in obj.identities:
            obj.identities.append(parent_ident)
        return parent_ident, None

    stmt = (
        select(StationaryPointRow)
        .join(
            IdentityStationaryLink,
            onclause=col(IdentityStationaryLink.stationary_id)
            == col(StationaryPointRow.id),
        )
        .join(
            IdentityRow,
            onclause=col(IdentityRow.id) == col(IdentityStationaryLink.identity_id),
        )
        .where(
            col(IdentityRow.algorithm_id) == parent_alg_id,
            col(IdentityRow.value) == parent_val,
        )
    )
    other_stps = ctx.session.scalars(stmt).all()
    other_geos = None
    if other_stps:
        other_geos = {
            ident.value: stp.geometry
            for stp in other_stps
            for ident in stp.identities
            if ident.algorithm.name == algorithm.name  # Filter by new algorithm name
            and stp.id != obj.id
        }
    return parent_ident, other_geos


def _attach_algorithm_identity(
    ctx: _IdentityFlushContext,
    obj: StationaryPointRow,
    algorithm: Algorithm,
    algorithm_val: str,
    parent_ident: IdentityRow | None,
) -> None:
    """Create (if needed) and attach the identity for `algorithm` to `obj`."""
    alg = (
        ctx.session.query(IdentityAlgorithmRow)
        .filter(col(IdentityAlgorithmRow.name) == algorithm.name)
        .one()
    )
    alg_id = _require_algorithm_id(alg)

    if algorithm.deterministic:
        algorithm_ident = _get_or_create_identity(ctx, alg_id, algorithm_val)
        if algorithm_ident not in obj.identities:
            obj.identities.append(algorithm_ident)
        return

    if parent_ident is None:
        msg = "Non-deterministic identifiers are required to have a parent identity."
        raise ValueError(msg)

    extra_key = (alg_id, algorithm_val)
    algorithm_ident = ctx.extra_cache.get(extra_key)
    if algorithm_ident is None:
        algorithm_ident = (
            ctx.session.query(IdentityExtraRow)
            .filter(
                col(IdentityExtraRow.algorithm_id) == alg_id,
                col(IdentityExtraRow.value) == algorithm_val,
            )
            .one_or_none()
        )
    if algorithm_ident is None:
        # The identity=parent_ident relationship lets SQLAlchemy
        # resolve the foreign key once `parent_ident` is flushed.
        algorithm_ident = IdentityExtraRow(
            identity=parent_ident,
            algorithm_id=alg_id,
            value=algorithm_val,
        )
        ctx.session.add(algorithm_ident)

    ctx.extra_cache[extra_key] = algorithm_ident


@event.listens_for(Session, "before_flush")
def add_registry_identities_before_flush(
    session: Session,
    flush_context: Any,  # noqa: ARG001, ANN401
    instances: Any,  # noqa: ARG001, ANN401
) -> None:
    """Automatically attach registry identities to newly inserted stationary points.

    Generates an identity for every registered algorithm except SMILES and Hill
    formula, which are attached as `IdentityExtraRow`s instead. Non-InChI
    algorithms are passed the InChI's sibling geometries as `other_geos`.
    """
    # Autoflush is suppressed while `before_flush` handlers run, so identities
    # created earlier in this same flush batch are not yet visible to the
    # `session.query(...)` lookups below. Cache them here (keyed by
    # algorithm id and value) so repeated lookups for the same identity
    # within this batch reuse the pending row instead of creating a
    # duplicate that collides with the `(algorithm_id, value)` unique
    # constraint once the flush actually executes.
    ctx = _IdentityFlushContext(session=session, cache={}, extra_cache={})

    for obj in session.new:
        if not isinstance(obj, StationaryPointRow):
            continue

        # Get geometry - try relationship first (for `geometry=geo_row`),
        # then load via FK (for `geometry_id=id`)
        geo_row = obj.geometry
        if geo_row is None and obj.geometry_id is not None:
            geo_row = session.get(GeometryRow, obj.geometry_id)

        if geo_row is None:
            # Without a geometry there is nothing to compute identities from.
            continue

        for algorithm in AlgorithmRegistry.algorithms:
            parent_ident, other_geos = _resolve_parent_identity(
                ctx, obj, algorithm, geo_row
            )
            algorithm_val = algorithm.identity_fn(geo_row, other_geos)
            _attach_algorithm_identity(ctx, obj, algorithm, algorithm_val, parent_ident)
