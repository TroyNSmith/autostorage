"""Trajectory row definition."""

from typing import TYPE_CHECKING

from sqlmodel import Relationship

from .core import BaseRow

if TYPE_CHECKING:
    from .link import CalculationTrajectoryLink, TrajectoryGeometryLink


class TrajectoryRow(BaseRow, table=True):
    """Ordered sequence of geometries from a calculation trajectory.

    Attributes
    ----------
    geometry_links
        Raw link rows connecting geometries to this trajectory.
    calculation_links
        Raw link rows connecting calculations to this trajectory.
    """

    __tablename__ = "trajectory"

    geometry_links: list["TrajectoryGeometryLink"] = Relationship(
        back_populates="trajectory"
    )
    calculation_links: list["CalculationTrajectoryLink"] = Relationship(
        back_populates="trajectory"
    )
