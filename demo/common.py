"""Common utilities for the demo."""

from pathlib import Path

import autogeom
import numpy as np
import orca
from sqlmodel import select

from autostorage import (
    AutostorageSession,
    CalculationGeometryLink,
    GeometryRow,
    ModelRow,
    PropertyValueRow,
    Role,
    StationaryPointRow,
)

OUT_DIR = Path(__file__).resolve().parent / "out"
DB_PATH = OUT_DIR / "demo.db"

PENT2ENE_SMILES = "C/C=C/CC"
PENT2ENE_INCHI = "InChI=1S/C5H10/c1-3-5-4-2/h3,5H,4H2,1-2H3/b5-3+"
HYDROXYL_SMILES = "[OH]"
HYDROXYL_INCHI = "InChI=1S/HO/h1H"


def get_or_create_model(sess: AutostorageSession, method: str) -> ModelRow:
    """Get the ORCA model for `method`, adding it to the session if new."""
    stmt = select(ModelRow).where(
        ModelRow.program == "ORCA",
        ModelRow.program_version == orca.version(),
        ModelRow.method == method,
    )
    model = sess.exec(stmt).first()
    if model is None:
        model = ModelRow(program="ORCA", program_version=orca.version(), method=method)
        sess.add(model)
    return model


def from_smiles(smiles: str) -> GeometryRow:
    """Convert a SMILES string to a GeometryRow."""
    return GeometryRow(**autogeom.from_smiles(smiles).model_dump())


def energy(geo: GeometryRow, model: ModelRow) -> float:
    """Return the energy stored for `geo` at `model`."""
    return next(
        float(prop.value)
        for prop in geo.properties
        if prop.property_kind_name == "energy" and prop.calculation.model == model
    )


def optimize(
    sess: AutostorageSession, geo: GeometryRow, model: ModelRow, work_dir: Path
) -> StationaryPointRow:
    """Optimize `geo` and store the result as a minimum with its energy and gradient.

    Identities (InChI, SMILES, ...) are attached to the new stationary point
    automatically when the session is flushed.
    """
    opt = orca.run(geo, model, "opt", work_dir)
    opt_geo = opt.geometry()
    opt.calculation.geometry_links.append(
        CalculationGeometryLink(geometry=opt_geo, role=Role.OUTPUT)
    )
    minimum = StationaryPointRow(calculation=opt.calculation, geometry=opt_geo)
    sess.add_all(
        [
            minimum,
            PropertyValueRow(
                property_kind_name="energy",
                calculation=opt.calculation,
                geometry=opt_geo,
                value=opt.energy(),
            ),
            PropertyValueRow(
                property_kind_name="gradient",
                calculation=opt.calculation,
                geometry=opt_geo,
                value=opt.gradient(),
            ),
        ]
    )
    return minimum
