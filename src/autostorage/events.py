"""SQLAlchemy ORM event listeners for validation and auto-managed identities."""

import uuid
from typing import Any

from automol import Geometry, Identity
from automol.ident import HILL_FORMULA, RDKIT_INCHI, RDKIT_SMILES, AlgorithmRegistry
from sqlalchemy import event
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapper, Session

from .models import (
    GeometryRow,
    GeometryTrajectoryLink,
    GradientRow,
    HessianRow,
    IdentityExtraRow,
    IdentityRow,
    StationaryPointRow,
    StepRow,
)


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


def _find_or_create_identity(session: Session, identity: Identity) -> IdentityRow:
    """Find or create an IdentityRow for the given Identity.

    Checks both the database and pending session inserts.
    """
    # First check the database
    existing = (
        session.query(IdentityRow)
        .filter_by(
            kind=identity.kind,
            algorithm=identity.algorithm,
            value=identity.value,
        )
        .first()
    )

    # If not in database, check session.new for pending inserts
    if existing is None:
        for new_obj in session.new:
            if (
                isinstance(new_obj, IdentityRow)
                and new_obj.kind == identity.kind
                and new_obj.algorithm == identity.algorithm
                and new_obj.value == identity.value
            ):
                existing = new_obj
                break

    if existing is None:
        # Create new identity row
        new_identity = IdentityRow(
            kind=identity.kind,
            algorithm=identity.algorithm,
            value=identity.value,
        )
        session.add(new_identity)
        return new_identity

    return existing


def _sibling_geometries(
    identity_row: IdentityRow, geometry_row: GeometryRow
) -> dict[str, Geometry]:
    """Return geometries sharing `identity_row`, keyed by id, sorted by ascending id.

    Excludes `geometry_row` itself and any sibling not yet assigned an id.
    """
    pairs: list[tuple[uuid.UUID, Geometry]] = [
        (sp.geometry.id, sp.geometry)
        for sp in identity_row.stationary_points
        if sp.geometry is not None
        and sp.geometry is not geometry_row
        and sp.geometry.id is not None
    ]
    return {str(geo_id): geo for geo_id, geo in sorted(pairs, key=lambda pair: pair[0])}


def _get_sibling_identity(
    session: Session, geometry_id: str, algorithm: str
) -> IdentityRow:
    """Get the identity for a sibling stationary point's geometry.

    Parameters
    ----------
    session
        Database session.
    geometry_id
        UUID string of the sibling geometry.
    algorithm
        Identity algorithm to retrieve.

    Returns
    -------
    IdentityRow
        The identity row for the sibling.

    Raises
    ------
    ValueError
        If no stationary point or identity is found.
    """
    sibling_geometry_id = uuid.UUID(geometry_id)
    sibling_sp = (
        session.query(StationaryPointRow)
        .filter_by(geometry_id=sibling_geometry_id)
        .first()
    )
    if sibling_sp is None:
        msg = f"No stationary point found for geometry {geometry_id}"
        raise ValueError(msg)

    identity_row = next(
        (id_row for id_row in sibling_sp.identities if id_row.algorithm == algorithm),
        None,
    )
    if identity_row is None:
        msg = f"Sibling stationary point {sibling_sp.id} missing {algorithm} identity"
        raise ValueError(msg)

    return identity_row


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
    algorithms = [
        alg
        for alg in AlgorithmRegistry.all_algorithms()
        if alg not in (RDKIT_SMILES, HILL_FORMULA)
    ]

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

        inchi_identity = Identity.from_geometry(geometry_row, algorithm=RDKIT_INCHI)
        inchi_row = _find_or_create_identity(session, inchi_identity)
        other_geos = _sibling_geometries(inchi_row, geometry_row)

        for algorithm in algorithms:
            if algorithm == RDKIT_INCHI:
                identity_row = inchi_row
            else:
                identity = Identity.from_geometry(
                    geometry_row, algorithm=algorithm, other_geos=other_geos
                )
                if identity.value in other_geos:
                    # Identity points to a sibling geometry - reuse that
                    # stationary point's identity
                    identity_row = _get_sibling_identity(
                        session, identity.value, algorithm
                    )
                else:
                    identity_row = _find_or_create_identity(session, identity)

            if identity_row not in obj.identities:
                obj.identities.append(identity_row)


def _find_or_create_identity_extra(
    session: Session, identity: IdentityRow, attribute: str, value: str
) -> IdentityExtraRow | None:
    """Find or create an IdentityExtraRow.

    Checks both the database and pending session inserts. Returns None if the
    extra already exists.
    """
    # Check if the identity has an ID (already in database)
    if identity.id is not None:
        existing = (
            session.query(IdentityExtraRow)
            .filter_by(
                identity_id=identity.id,
                attribute=attribute,
                value=value,
            )
            .first()
        )
        if existing is not None:
            return None  # Already exists in database

    # Check session.new for pending inserts (both for this identity and in general)
    for new_obj in session.new:
        if (
            isinstance(new_obj, IdentityExtraRow)
            and (new_obj.identity is identity or new_obj.identity_id == identity.id)
            and new_obj.attribute == attribute
            and new_obj.value == value
        ):
            return None  # Already pending insertion

    # Create new extra, using the identity relationship
    return IdentityExtraRow(
        identity=identity,
        attribute=attribute,
        value=value,
    )


@event.listens_for(Session, "before_flush")
def add_smiles_extras_before_flush(
    session: Session,
    flush_context: Any,  # noqa: ARG001, ANN401
    instances: Any,  # noqa: ARG001, ANN401
) -> None:
    """Automatically attach SMILES as IdentityExtraRow to stationary points."""
    for obj in session.new:
        if not isinstance(obj, StationaryPointRow):
            continue

        # Skip if no identities attached yet
        if not obj.identities:
            continue

        # Get geometry - try relationship first (for `geometry=geo_row`),
        # then load via FK (for `geometry_id=id`)
        geometry_row = obj.geometry
        if geometry_row is None and obj.geometry_id is not None:
            geometry_row = session.get(GeometryRow, obj.geometry_id)
        if geometry_row is None:
            continue

        # Generate SMILES from geometry
        try:
            smiles_identity = Identity.from_geometry(
                geometry_row, algorithm=RDKIT_SMILES
            )
            smiles_value = smiles_identity.value
        except Exception:  # noqa: BLE001, S112
            # Skip if SMILES generation fails (e.g., invalid structure)
            continue

        # Get the InChI identity (attached by add_registry_identities_before_flush)
        inchi_identity = next(
            (ident for ident in obj.identities if ident.algorithm == RDKIT_INCHI),
            None,
        )

        if inchi_identity is None:
            continue

        # Find or create the SMILES extra
        smiles_extra = _find_or_create_identity_extra(
            session, inchi_identity, "rdkit_smiles", smiles_value
        )

        if smiles_extra is not None:
            session.add(smiles_extra)


@event.listens_for(Session, "before_flush")
def add_hill_extras_before_flush(
    session: Session,
    flush_context: Any,  # noqa: ARG001, ANN401
    instances: Any,  # noqa: ARG001, ANN401
) -> None:
    """Automatically attach Hill formula as IdentityExtraRow to stationary points."""
    for obj in session.new:
        if not isinstance(obj, StationaryPointRow):
            continue

        # Skip if no identities attached yet
        if not obj.identities:
            continue

        # Get geometry - try relationship first (for `geometry=geo_row`),
        # then load via FK (for `geometry_id=id`)
        geometry_row = obj.geometry
        if geometry_row is None and obj.geometry_id is not None:
            geometry_row = session.get(GeometryRow, obj.geometry_id)
        if geometry_row is None:
            continue

        # Generate Hill formula from geometry
        try:
            hill_identity = Identity.from_geometry(geometry_row, algorithm=HILL_FORMULA)
            hill_value = hill_identity.value
        except Exception:  # noqa: BLE001, S112
            # Skip if Hill formula generation fails (e.g., invalid structure)
            continue

        # Get the InChI identity (attached by add_registry_identities_before_flush)
        inchi_identity = next(
            (ident for ident in obj.identities if ident.algorithm == RDKIT_INCHI),
            None,
        )

        if inchi_identity is None:
            continue

        # Find or create the Hill formula extra
        hill_extra = _find_or_create_identity_extra(
            session, inchi_identity, "hill_formula", hill_value
        )

        if hill_extra is not None:
            session.add(hill_extra)
