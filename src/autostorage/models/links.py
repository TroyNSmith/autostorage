"""Linker models."""

from typing import TYPE_CHECKING, Any

from pydantic import ConfigDict
from sqlmodel import JSON, Column, Field, Relationship

from ..types import Role, RowID
from .base import BaseRow

if TYPE_CHECKING:
    from .calculation import CalculationRow
    from .geometry import GeometryRow
    from .trajectory import TrajectoryRow  # noqa: F401


class CalculationGeometryLink(BaseRow, table=True):
    """
    Link CalculationRows to GeometryRows.

    Attributes
    ----------
    geometry_id
        Foreign key to the linked geometry.
    calculation_id
        Foreign key to the linked calculation.
    role
        Role of the geometry in the calculation.
    [SQL] calculation
        Corresponding CalculationRow.
    [SQL] geometry
        Corresponding role GeometryRow.
    """

    # - SQL Metadata ------------------
    __tablename__ = "calculation_geometry_link"
    model_config = ConfigDict(use_enum_values=True)
    # - Row id ------------------------
    # - Foreign keys ------------------
    calculation_id: RowID = Field(
        foreign_key="calculation.id", primary_key=True, ondelete="CASCADE"
    )
    geometry_id: RowID = Field(
        foreign_key="geometry.id", primary_key=True, ondelete="CASCADE"
    )
    # - Attributes --------------------
    role: Role = Field(description="Role of the geometry in the calculation.")
    # - SQLModel relationships --------
    calculation: "CalculationRow" = Relationship(back_populates="geometry_links")
    geometry: "GeometryRow" = Relationship(back_populates="calculation_links")


class StationaryIdentityLink(BaseRow, table=True):
    """
    Link StationaryPointRow to IdentityRow.

    Attributes
    ----------
    stationary_id
        Foreign key to the linked stationary point.
    identity_id
        Foreign key to the linked identity.
    """

    # - SQL Metadata ------------------
    __tablename__ = "stationary_identity_link"
    # - Row id ------------------------
    # - Foreign keys ------------------
    stationary_id: RowID = Field(
        foreign_key="stationary_point.id", primary_key=True, ondelete="CASCADE"
    )
    identity_id: RowID = Field(
        foreign_key="identity.id", primary_key=True, ondelete="CASCADE"
    )
    # - Attributes --------------------
    # - SQLModel relationships --------


class StationaryStageLink(BaseRow, table=True):
    """
    Link StationaryPointRows to StageRows.

    Attributes
    ----------
    stationary_id
        Foreign key to the linked stationary point.
    stage_id
        Foreign key to the linked reaction stage.
    """

    # - SQL Metadata ------------------
    __tablename__ = "stationary_stage_link"
    # - Row id ------------------------
    # - Foreign keys ------------------
    stationary_id: RowID = Field(
        foreign_key="stationary_point.id", primary_key=True, ondelete="CASCADE"
    )
    stage_id: RowID = Field(
        foreign_key="stage.id", primary_key=True, ondelete="CASCADE"
    )
    # - Attributes --------------------
    # - SQLModel relationships --------


class CalculationTrajectoryLink(BaseRow, table=True):
    """
    Link CalculationRow to TrajectoryRow.

    Attributes
    ----------
    stationary_id
        Foreign key to the linked stationary point.
    identity_id
        Foreign key to the linked identity.
    """

    # - SQL Metadata ------------------
    __tablename__ = "calculation_trajectory_link"
    # - Row id ------------------------
    # - Foreign keys ------------------
    calculation_id: RowID = Field(
        foreign_key="calculation.id", primary_key=True, ondelete="CASCADE"
    )
    trajectory_id: RowID = Field(
        foreign_key="trajectory.id", primary_key=True, ondelete="CASCADE"
    )
    # - Attributes --------------------
    # - SQLModel relationships --------


class TrajectoryGeometryLink(BaseRow, table=True):
    """
    Geometry at a point along the trajectory.

    Attributes
    ----------
    id
        Primary key.
    trajectory_id
        Foreign key to the parent trajectory.
    geometry_id
        Foreign key to the child geometry.
    coordinate
        Coordinate step along the trajectory sequence.
        1D: [int]
        2D: [int, int]
        ...
    extras
        Additional metadata for this point.
    [SQL] trajectory
        Parent trajectory.
    [SQL] geometry
        Child geometry.
    """

    # - SQL Metadata ------------------
    __tablename__ = "trajectory_geometry_link"
    # - Row id ------------------------
    id: RowID | None = Field(default=None, primary_key=True)
    # - Foreign keys ------------------
    trajectory_id: RowID = Field(foreign_key="trajectory.id", ondelete="CASCADE")
    geometry_id: RowID = Field(foreign_key="geometry.id", ondelete="CASCADE")
    # - Attributes --------------------
    coordinate: list[int] | None = Field(default_factory=list, sa_column=Column(JSON))
    extras: dict[str, Any] | None = Field(default_factory=dict, sa_column=Column(JSON))
    # - SQL relationships -------------
