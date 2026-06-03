"""Model listeners."""

from automol import geom
from sqlalchemy import event
from sqlmodel import Session, select

from ..calcn import calculation_hash, hash_registry
from .calculation import CalculationHashRow, CalculationRow
from .geometry import GeometryRow
from .links import StationaryIdentityLink
from .stationary import IdentityExtraRow, IdentityRow, StationaryPointRow


@event.listens_for(GeometryRow, "before_insert")
def populate_geometry_hash(mapper, connection, target: GeometryRow) -> None:  # noqa: ANN001, ARG001
    """Populate GeometryRow hash before inserts and updates."""
    if target.hash is None:
        target.hash = geom.geometry_hash(target)


@event.listens_for(Session, "after_flush")
def populate_calculation_hashes(session, flush_context) -> None:  # noqa: ANN001, ARG001
    """Populate the 'minimal' hash for newly added CalculationRow objects."""
    available = set(hash_registry.available())

    for row in session.new:
        if not isinstance(row, CalculationRow):
            continue

        existing = {h.name for h in row.hashes}
        missing = available - existing
        if not missing:
            continue

        calc = row

        for name in missing:
            value = calculation_hash(calc, name=name)

            session.add(
                CalculationHashRow(
                    calculation_id=row.id,
                    name=name,
                    value=value,
                )
            )


@event.listens_for(StationaryPointRow, "after_insert")
def on_stationary_point_insert(mapper, connection, target: StationaryPointRow) -> None:  # noqa: ANN001, ARG001
    """Auto-tag InChI identity after inserting a StationaryPoint."""
    session = Session(bind=connection)
    try:
        _attach_inchi(session, target)
        session.commit()
    except Exception as e:
        session.rollback()
        msg = f"Failed to generate InChI for StationaryPoint id={target.id!r}."
        raise RuntimeError(msg) from e


def _attach_inchi(session: Session, target: StationaryPointRow) -> None:
    """Compute and link an InChI identity with extra SMILES to a StationaryPointRow."""
    if target.id is None:
        msg = f"Row id failed to attach to {target = }."
        raise ValueError(msg)

    geo_row = session.get(GeometryRow, target.geometry_id)

    if geo_row is None:
        msg = f"GeometryRow not found for id={target.geometry_id}."
        raise LookupError(msg)

    inchi_row = IdentityRow.from_geometry(geo=geo_row, algorithm="rdkit inchi")
    smiles_row = IdentityRow.from_geometry(geo=geo_row, algorithm="rdkit smiles")

    existing_row = session.exec(
        select(IdentityRow).where(
            IdentityRow.algorithm == inchi_row.algorithm,
            IdentityRow.value == inchi_row.value,
        )
    ).first()

    if existing_row is None:
        session.add(inchi_row)
        session.flush()
        existing_row = inchi_row

    if existing_row.id is None:
        msg = f"Row id failed to attach to {target = }."
        raise ValueError(msg)

    session.add(
        StationaryIdentityLink(stationary_id=target.id, identity_id=existing_row.id)
    )

    session.add(
        IdentityExtraRow(
            identity_id=existing_row.id,
            attribute=smiles_row.algorithm,
            value=smiles_row.value,
        )
    )
