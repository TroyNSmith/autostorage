"""Molecular geometry row definition."""

import hashlib
import json
from typing import TYPE_CHECKING, Self

import numpy as np
from automol import Geometry
from automol.utils.types import FloatArray
from sqlmodel import JSON, Column, Field, Relationship, UniqueConstraint, select
from sqlmodel.main import SQLModelConfig

from autostorage.types import CompressedArrayTypeDecorator

from .core import BaseRow

if TYPE_CHECKING:
    from autostorage.database import Database

    from .data import EnergyRow, GradientRow, HessianRow
    from .link import CalculationGeometryLink, TrajectoryGeometryLink
    from .rxn import StationaryPointRow


def _geometry_hash(
    symbols: list[str], coordinates: FloatArray, charge: int, spin: int
) -> str:
    """Compute a hash identifying bit-identical geometry content."""
    hasher = hashlib.sha256()
    hasher.update(json.dumps(symbols).encode())
    hasher.update(np.asarray(coordinates, dtype=np.float64).tobytes())
    hasher.update(charge.to_bytes(8, "big", signed=True))
    hasher.update(spin.to_bytes(8, "big", signed=True))
    return hasher.hexdigest()


# Geometry table
class GeometryRow(BaseRow, table=True):
    """Molecular geometry definition and metadata.

    Attributes
    ----------
    symbols
        Atomic symbols in order.
    coordinates
        Atomic coordinates in Angstrom.
    charge
        Total molecular charge.
    spin
        Number of unpaired electrons (2S).
    geometry_hash
        Content hash of `symbols`/`coordinates`/`charge`/`spin`, used to reject
        exactly-duplicate geometries (see `find_or_create`).
    energies
        Energy results computed at this geometry.
    gradients
        Gradient results computed at this geometry.
    hessians
        Hessian results computed at this geometry.
    stationary_points
        Stationary points defined by this geometry.
    trajectory_links
        Raw link rows connecting this geometry to trajectories.
    calculation_links
        Raw link rows connecting this geometry to calculations.
    """

    __tablename__ = "geometry"
    __table_args__ = (UniqueConstraint("geometry_hash", name="unique_geometry_hash"),)
    model_config = SQLModelConfig(arbitrary_types_allowed=True)

    symbols: list[str] = Field(sa_column=Column(JSON))
    coordinates: FloatArray = Field(sa_column=Column(CompressedArrayTypeDecorator()))
    charge: int
    spin: int
    geometry_hash: str | None = Field(default=None, nullable=False)

    energies: list["EnergyRow"] = Relationship(back_populates="geometry")
    gradients: list["GradientRow"] = Relationship(back_populates="geometry")
    hessians: list["HessianRow"] = Relationship(back_populates="geometry")
    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="geometry"
    )
    trajectory_links: list["TrajectoryGeometryLink"] = Relationship(
        back_populates="geometry"
    )
    calculation_links: list["CalculationGeometryLink"] = Relationship(
        back_populates="geometry"
    )

    def to_geometry(self) -> Geometry:
        """Convert to an automol Geometry instance."""
        return Geometry(
            symbols=self.symbols,
            coordinates=self.coordinates,
            charge=self.charge,
            spin=self.spin,
        )

    @classmethod
    def find_or_create(  # noqa: PLR0913
        cls,
        db: "Database",
        *,
        symbols: list[str],
        coordinates: FloatArray,
        charge: int,
        spin: int,
        commit: bool = True,
    ) -> Self:
        """Return the matching geometry row, creating and saving one if absent.

        Matches on exact content via `geometry_hash`, so this only reuses
        bit-identical geometries.

        Parameters
        ----------
        commit, optional
            If True (default), commit a newly-created row immediately. If
            False, only flush it (still assigns `.id`), leaving the caller's
            transaction open — for a caller staging several dedup lookups
            that must succeed or fail together.
        """
        geometry_hash = _geometry_hash(symbols, coordinates, charge, spin)
        stmt = select(cls).where(cls.geometry_hash == geometry_hash)
        existing = db.exec_first(stmt)
        if existing is not None:
            return existing

        row = cls(symbols=symbols, coordinates=coordinates, charge=charge, spin=spin)
        db.add(row)
        if commit:
            db.commit()
        else:
            db.flush()
        return row
