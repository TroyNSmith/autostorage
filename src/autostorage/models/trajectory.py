"""Trajectory models."""

from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship

from ..types import RowID
from .base import BaseRow
from .links import CalculationTrajectoryLink, TrajectoryGeometryLink

if TYPE_CHECKING:
    from .calculation import CalculationRow
    from .geometry import GeometryRow


class TrajectoryRow(BaseRow, table=True):
    """
    Trajectory primary container.

    Attributes
    ----------
    id
        Primary key.
    [SQL] calculation
        Parent calculation.
    """

    # - SQL Metadata ------------------
    __tablename__ = "trajectory"
    # - Row id ------------------------
    id: RowID | None = Field(default=None, primary_key=True)
    # - Foreign keys ------------------
    # - Attributes --------------------
    # - SQL relationships -------------
    calculation: "CalculationRow" = Relationship(
        back_populates="trajectories", link_model=CalculationTrajectoryLink
    )
    geometries: list["GeometryRow"] = Relationship(
        back_populates="trajectory", link_model=TrajectoryGeometryLink
    )
