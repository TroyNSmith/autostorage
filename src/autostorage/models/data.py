"""Result row definitions (energy, gradient, Hessian)."""

from functools import cached_property
from typing import TYPE_CHECKING

import numpy as np
from automol import geom
from automol.utils.types import FloatArray
from sqlmodel import Column, Field, Relationship, SQLModel
from sqlmodel.main import SQLModelConfig

from autostorage.types import CompressedArrayTypeDecorator, _fk_field

if TYPE_CHECKING:
    from .calc import CalculationRow
    from .geom import GeometryRow


class EnergyRow(SQLModel, table=True):
    """Energy result for a specific geometry and calculation.

    Attributes
    ----------
    geometry_id
        Foreign key to the geometry this energy was evaluated at.
    calculation_id
        Foreign key to the calculation that produced this energy.
    value
        Energy value in Hartree.
    geometry
        Geometry this energy was evaluated at.
    calculation
        Calculation that produced this energy.
    """

    __tablename__ = "energy"

    id: int | None = Field(default=None, primary_key=True)
    geometry_id: int | None = _fk_field("geometry.id")
    calculation_id: int | None = _fk_field("calculation.id")
    value: float

    calculation: "CalculationRow" = Relationship()
    geometry: "GeometryRow" = Relationship(back_populates="energies")


class GradientRow(SQLModel, table=True):
    """Energy gradient result for a specific geometry and calculation.

    Attributes
    ----------
    geometry_id
        Foreign key to the geometry this gradient was evaluated at.
    calculation_id
        Foreign key to the calculation that produced this gradient.
    value
        Flattened gradient vector in Hartree/Bohr.
    geometry
        Geometry this gradient was evaluated at.
    calculation
        Calculation that produced this gradient.
    """

    __tablename__ = "gradient"
    model_config = SQLModelConfig(arbitrary_types_allowed=True)

    id: int | None = Field(default=None, primary_key=True)
    geometry_id: int | None = _fk_field("geometry.id")
    calculation_id: int | None = _fk_field("calculation.id")
    value: FloatArray = Field(sa_column=Column(CompressedArrayTypeDecorator()))

    calculation: "CalculationRow" = Relationship()
    geometry: "GeometryRow" = Relationship(back_populates="gradients")


class HessianRow(SQLModel, table=True):
    """Hessian result for a specific geometry and calculation.

    Attributes
    ----------
    geometry_id
        Foreign key to the geometry this Hessian was evaluated at.
    calculation_id
        Foreign key to the calculation that produced this Hessian.
    value
        Hessian matrix in Hartree/Bohr^2.
    geometry
        Geometry this Hessian was evaluated at.
    calculation
        Calculation that produced this Hessian.
    """

    __tablename__ = "hessian"
    model_config = SQLModelConfig(arbitrary_types_allowed=True)

    id: int | None = Field(default=None, primary_key=True)
    geometry_id: int | None = _fk_field("geometry.id")
    calculation_id: int | None = _fk_field("calculation.id")

    value: np.ndarray = Field(
        sa_column=Column(CompressedArrayTypeDecorator(dtype=np.float32))
    )

    calculation: "CalculationRow" = Relationship()
    geometry: "GeometryRow" = Relationship(back_populates="hessians")

    @cached_property
    def harmonic_frequencies(self) -> tuple[float, ...]:
        """Harmonic frequencies derived from the Hessian.

        Cached per instance, since vibrational analysis re-diagonalizes the
        Hessian on every call and `.order` (used by `_recompute_geometry_
        stationary_validity` for every sibling Hessian of a geometry, on
        every relevant flush) depends on it. Invalidated on `value` update
        by `invalidate_hessian_frequency_cache` in `events.py`.
        """
        freqs, _ = geom.vibrational_analysis(
            geo=self.geometry.to_geometry(), hess=self.value
        )
        return freqs

    @property
    def order(self) -> int:
        """Hessian order."""
        return sum(1 for f in self.harmonic_frequencies if f < 0.0)
