"""Test for models module."""

import numpy as np
from automol import Geometry

from autostorage import Calculation, Database
from autostorage.models import (
    CalculationRow,
    GeometryRow,
    StationaryPointRow,
)


def test__calculation_calculation_row_equivalence(calc: Calculation) -> None:
    """Test data persistence for Calculation -> CalculationRow."""
    calc_row = CalculationRow.from_calculation(calc)

    assert calc.program == calc_row.program
    assert calc.program_keywords == calc_row.program_keywords
    assert calc.super_program == calc_row.super_program
    assert calc.super_keywords == calc_row.super_keywords
    assert calc.cmdline_args == calc_row.cmdline_args
    assert calc.calc_type == calc_row.calc_type
    assert calc.method == calc_row.method
    assert calc.basis == calc_row.basis


def test__geometry_geometry_row_equivalence(geo: Geometry) -> None:
    """Test data persistence for Geometry -> GeometryRow."""
    geo_row = GeometryRow.from_geometry(geo=geo)

    assert np.array_equal(a1=geo_row.symbols, a2=geo.symbols)
    assert np.allclose(a=geo_row.coordinates, b=geo.coordinates)
    assert geo_row.charge == geo.charge
    assert geo_row.spin == geo_row.spin


def test__stationary_point_inchi(
    database: Database, calc_row: CalculationRow, geo_row: GeometryRow
) -> None:
    """Test automatic InChI tagging for stationary point."""
    assert calc_row.id is not None
    assert geo_row.id is not None

    stp_row = StationaryPointRow(
        calculation_id=calc_row.id, geometry_id=geo_row.id, order=0, is_pseudo=True
    )
    database.add(stp_row)

    assert stp_row.identities[0].value == "InChI=1S/H2O/h1H2"


def test__comparison(calc_row: CalculationRow) -> None:
    """Test comparison mixin."""
    calc_row2 = calc_row.model_copy(deep=True)

    assert calc_row == calc_row2
