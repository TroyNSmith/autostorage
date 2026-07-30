"""Trajectory row definition."""

from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .link import CalculationTrajectoryLink, TrajectoryGeometryLink


class TrajectoryRow(SQLModel, table=True):
    """Ordered sequence of geometries from a calculation trajectory.

    Attributes
    ----------
    geometry_links
        Raw link rows connecting geometries to this trajectory.
    calculation_links
        Raw link rows connecting calculations to this trajectory.
    """

    __tablename__ = "trajectory"

    id: int | None = Field(default=None, primary_key=True)

    geometry_links: list["TrajectoryGeometryLink"] = Relationship(
        back_populates="trajectory"
    )
    calculation_links: list["CalculationTrajectoryLink"] = Relationship(
        back_populates="trajectory"
    )
