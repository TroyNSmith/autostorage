"""Geometry models."""

from typing import TYPE_CHECKING

from automol import Geometry
from automol.types import FloatArray
from pydantic import ConfigDict
from sqlalchemy.types import JSON, String
from sqlmodel import Column, Field, Relationship

from ..types import FloatArrayTypeDecorator, RowID
from .base import BaseRow
from .links import CalculationGeometryLink, TrajectoryGeometryLink

if TYPE_CHECKING:
    from .data import EnergyRow
    from .stationary import StationaryPointRow
    from .trajectory import TrajectoryRow


class GeometryRow(BaseRow, Geometry, table=True):
    """
    Molecular geometry definition and metadata.

    Attributes
    ----------
    symbols
        List of atomic symbols in order.
    coordinates
        Atomic coordinates in Angstrom.
    charge
        Total molecular charge.
    spin
        Number of unpaired electrons (2S).
    hash
        Unique hash of the geometry for indexing.
    [SQL] calculation_links
        List of linked CalculationGeometryLinks allowing access to Role directly.
    [SQL] energies
        List of calculated energies for this geometry.
    [SQL] stationary_points
        StationaryPointRow associated with this geometry.
    """

    # - SQL Metadata ------------------
    __tablename__ = "geometry"
    model_config = ConfigDict(arbitrary_types_allowed=True)
    # - Row id ------------------------
    id: RowID | None = Field(default=None, primary_key=True)
    # - Foreign keys ------------------
    # - Attributes --------------------
    symbols: list[str] = Field(sa_column=Column(JSON))
    coordinates: FloatArray = Field(sa_column=Column(FloatArrayTypeDecorator))
    charge: int = Field(default=0)
    spin: int = Field(default=0)
    hash: str | None = Field(
        default=None,
        sa_column=Column(String(64), index=True, nullable=True, unique=True),
    )
    # ^ Populated by event listener
    # - SQLModel relationships --------
    calculation_links: list["CalculationGeometryLink"] = Relationship(
        back_populates="geometry"
    )
    energies: list["EnergyRow"] = Relationship(
        back_populates="geometry", cascade_delete=True
    )
    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="geometry"
    )
    trajectory: "TrajectoryRow" = Relationship(
        back_populates="geometries", link_model=TrajectoryGeometryLink
    )

    # - Methods -----------------------
    @staticmethod
    def from_geometry(geo: Geometry) -> "GeometryRow":
        """
        Instantiate GeometryRow from Geometry.

        Returns
        -------
        GeometryRow
        """
        return GeometryRow(**geo.model_dump())
