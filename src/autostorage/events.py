"""SQLAlchemy ORM event listeners for validation and auto-managed identities."""

import uuid
from typing import Any

from automol import Geometry, HillFormula, Identity, RDKitInChI, RDKitSMILES
from automol.ident import AlgorithmRegistry
from sqlalchemy import event
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapper, Session

from .models import (
    GeometryRow,
    GeometryTrajectoryLink,
    GradientRow,
    HessianRow,
    IdentityAlgorithmRow,
    IdentityExtraRow,
    IdentityRow,
    StationaryPointRow,
    StepRow,
)


def create_parent_identity_algorithms(session: Session) -> None:
    """Create identity algorithms in the database if they do not already exist."""
    for alg in AlgorithmRegistry.algorithms:
        if alg.parent_algorithm is not None:
            continue

        existing = session.query(IdentityAlgorithmRow).filter_by(name=alg.name).first()
        if existing is None:
            session.add(IdentityAlgorithmRow(name=alg.name, kind=alg.kind))

    session.commit()
    session.close()


def create_child_identity_algorithms(session: Session) -> None:
    """Create child identity algorithms in the database if they do not already exist."""
    for alg in AlgorithmRegistry.algorithms:
        if alg.parent_algorithm is None:
            continue

        existing = session.query(IdentityAlgorithmRow).filter_by(name=alg.name).first()
        if existing is None:
            parent = (
                session.query(IdentityAlgorithmRow)
                .filter_by(name=alg.parent_algorithm.name)
                .one()
            )
            session.add(
                IdentityAlgorithmRow(
                    name=alg.name,
                    kind=alg.kind,
                    parent_algorithm_id=parent.id,
                )
            )

    session.commit()
    session.close()


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
    pending_identities: dict[tuple[int | None, str], IdentityRow] = {}
    pending_extras: dict[tuple[int | None, str], IdentityExtraRow] = {}

    for obj in session.new:
        if not isinstance(obj, StationaryPointRow):
            continue

        # Get geometry - try relationship first (for `geometry=geo_row`),
        # then load via FK (for `geometry_id=id`)
        geometry_row = obj.geometry
        if geometry_row is None and obj.geometry_id is not None:
            geometry_row = session.get(GeometryRow, obj.geometry_id)
        if geometry_row is None:
            continue

        for algorithm in AlgorithmRegistry.algorithms:
            if algorithm.is_extra:
                continue

            algorithm_row = (
                session.query(IdentityAlgorithmRow).filter_by(name=algorithm.name).one()
            )
            other_geos = None

            parent_algorithm = algorithm.parent_algorithm
            if parent_algorithm is not None:
                _parent_algorithm = (
                    session.query(IdentityAlgorithmRow)
                    .filter_by(name=parent_algorithm.name)
                    .one()
                )
                _parent_value = parent_algorithm.identity_fn(geometry_row)
                _cache_key = (_parent_algorithm.id, _parent_value)
                _parent_identity = pending_identities.get(_cache_key) or (
                    session.query(IdentityRow)
                    .filter_by(
                        algorithm_id=_parent_algorithm.id,
                        value=_parent_value,
                    )
                    .first()
                )
                if _parent_identity is not None:
                    other_geos = {
                        i.value: s.geometry
                        for s in _parent_identity.stationary_points
                        for i in s.identities
                        if i.algorithm_id == algorithm_row.id
                    }

            identity_value = algorithm.identity_fn(geometry_row, other_geos=other_geos)
            cache_key = (algorithm_row.id, identity_value)
            identity = pending_identities.get(cache_key) or (
                session.query(IdentityRow)
                .filter_by(
                    algorithm_id=algorithm_row.id,
                    value=identity_value,
                )
                .first()
            )
            if identity is None:
                identity = IdentityRow(
                    algorithm_id=algorithm_row.id,
                    value=identity_value,
                )
                session.add(identity)
                pending_identities[cache_key] = identity

            identity.stationary_points.append(obj)

        for algorithm in AlgorithmRegistry.algorithms:
            if not algorithm.is_extra:
                continue

            algorithm_row = (
                session.query(IdentityAlgorithmRow).filter_by(name=algorithm.name).one()
            )
            other_geos = None

            parent_algorithm = algorithm.parent_algorithm or RDKitInChI
            _parent_algorithm = (
                session.query(IdentityAlgorithmRow)
                .filter_by(name=parent_algorithm.name)
                .one()
            )
            _parent_value = parent_algorithm.identity_fn(geometry_row)
            _cache_key = (_parent_algorithm.id, _parent_value)
            _parent_identity = pending_identities.get(_cache_key) or (
                session.query(IdentityRow)
                .filter_by(
                    algorithm_id=_parent_algorithm.id,
                    value=_parent_value,
                )
                .one()
            )
            if _parent_identity is not None:
                other_geos = {
                    i.value: s.geometry
                    for s in _parent_identity.stationary_points
                    for i in s.identities
                    if i.algorithm_id == algorithm_row.id
                }

            identity_value = algorithm.identity_fn(geometry_row, other_geos=other_geos)
            cache_key = (algorithm_row.id, identity_value)
            identity = pending_extras.get(cache_key) or (
                session.query(IdentityExtraRow)
                .filter_by(
                    algorithm_id=algorithm_row.id,
                    value=identity_value,
                )
                .first()
            )
            if identity is None:
                identity = IdentityExtraRow(
                    algorithm_id=algorithm_row.id,
                    value=identity_value,
                )
                session.add(identity)
                pending_extras[cache_key] = identity

            _parent_identity.identity_extras.append(identity)
