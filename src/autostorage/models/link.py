"""Association tables linking row entities together."""

from typing import TYPE_CHECKING

from sqlmodel import JSON, Column, Enum, Field, Index, Relationship, SQLModel

from autostorage.types import Role

if TYPE_CHECKING:
    from .calc import CalculationRow
    from .geom import GeometryRow
    from .traj import TrajectoryRow


class TrajectoryGeometryLink(SQLModel, table=True):
    """Association table linking geometries to a trajectory.

    Attributes
    ----------
    geometry_id
        Foreign key to the linked geometry.
    trajectory_id
        Foreign key to the linked trajectory.
    index
        Position of the geometry within the trajectory.
    geometry
        The linked geometry.
    trajectory
        The linked trajectory.
    """

    __tablename__ = "trajectory_geometry_link"
    __table_args__ = (
        Index("ix_trajectory_geometry_link_trajectory_id", "trajectory_id"),
    )

    geometry_id: int | None = Field(
        default=None,
        foreign_key="geometry.id",
        primary_key=True,
        ondelete="CASCADE",
        nullable=False,
    )
    trajectory_id: int | None = Field(
        default=None,
        foreign_key="trajectory.id",
        primary_key=True,
        ondelete="CASCADE",
        nullable=False,
    )
    index: list[int] | None = Field(default=None, sa_column=Column(JSON))

    geometry: "GeometryRow" = Relationship(back_populates="trajectory_links")
    trajectory: "TrajectoryRow" = Relationship(back_populates="geometry_links")


# Link tables declared here, ahead of the StationaryPointRow/IdentityRow and
# StationaryPointRow/StageRow entities they connect, because SQLModel's
# `link_model=` kwarg needs the actual class object at class-body-evaluation
# time — unlike every other cross-model reference in this file, it can't be
# satisfied by a lazily-resolved string forward ref.
class StationaryIdentityLink(SQLModel, table=True):
    """Association table linking stationary points to chemical identities.

    Attributes
    ----------
    stationary_id
        Foreign key to the linked stationary point.
    identity_id
        Foreign key to the linked identity.
    """

    __tablename__ = "stationary_identity_link"
    __table_args__ = (Index("ix_stationary_identity_link_identity_id", "identity_id"),)

    stationary_id: int = Field(
        foreign_key="stationary_point.id",
        primary_key=True,
        ondelete="CASCADE",
        nullable=False,
    )
    identity_id: int = Field(
        foreign_key="identity.id",
        primary_key=True,
        ondelete="CASCADE",
        nullable=False,
    )


class StationaryStageLink(SQLModel, table=True):
    """Association table linking stationary points to reaction stages.

    Attributes
    ----------
    stationary_id
        Foreign key to the linked stationary point.
    stage_id
        Foreign key to the linked reaction stage.
    stationary
        The linked stationary point.
    stage
        The linked reaction stage.
    """

    __tablename__ = "stationary_stage_link"
    __table_args__ = (Index("ix_stationary_stage_link_stage_id", "stage_id"),)

    stationary_id: int | None = Field(
        default=None,
        foreign_key="stationary_point.id",
        primary_key=True,
        ondelete="CASCADE",
        nullable=False,
    )
    stage_id: int | None = Field(
        default=None,
        foreign_key="stage.id",
        primary_key=True,
        ondelete="CASCADE",
        nullable=False,
    )


# Declared here, ahead of StepRow, for the same `link_model=` reason as
# StationaryIdentityLink/StationaryStageLink above.
class StepValidationLink(SQLModel, table=True):
    """Association table linking validations to a step.

    Attributes
    ----------
    step_id
        Foreign key to the linked step.
    validation_id
        Foreign key to the linked validation.
    """

    __tablename__ = "step_validation_link"
    __table_args__ = (Index("ix_step_validation_link_validation_id", "validation_id"),)

    step_id: int = Field(
        foreign_key="step.id",
        primary_key=True,
        ondelete="CASCADE",
        nullable=False,
    )
    validation_id: int = Field(
        foreign_key="validation.id",
        primary_key=True,
        ondelete="CASCADE",
        nullable=False,
    )


class CalculationGeometryLink(SQLModel, table=True):
    """Association table linking geometries to a calculation.

    Attributes
    ----------
    geometry_id
        Foreign key to the linked geometry.
    calculation_id
        Foreign key to the linked calculation.
    role
        Role the geometry plays for this calculation (input/output).
    geometry
        The linked geometry.
    calculation
        The linked calculation.
    """

    __tablename__ = "calculation_geometry_link"
    __table_args__ = (
        # The composite primary key only serves lookups keyed by `geometry_id`
        # (its leading column); this adds a matching index for `calculation_id`.
        Index("ix_calculation_geometry_link_calculation_id", "calculation_id"),
    )

    geometry_id: int | None = Field(
        default=None,
        foreign_key="geometry.id",
        ondelete="CASCADE",
        nullable=False,
        primary_key=True,
    )
    calculation_id: int | None = Field(
        default=None,
        foreign_key="calculation.id",
        ondelete="CASCADE",
        nullable=False,
        primary_key=True,
    )
    role: Role = Field(
        sa_column=Column(Enum(Role, values_callable=lambda x: [e.value for e in x]))
    )

    geometry: "GeometryRow" = Relationship(back_populates="calculation_links")
    calculation: "CalculationRow" = Relationship(back_populates="geometry_links")


class CalculationTrajectoryLink(SQLModel, table=True):
    """Association table linking trajectories to a calculation.

    Attributes
    ----------
    trajectory_id
        Foreign key to the linked trajectory.
    calculation_id
        Foreign key to the linked calculation.
    role
        Role the trajectory plays for this calculation (input/output).
    trajectory
        The linked trajectory.
    calculation
        The linked calculation.
    """

    __tablename__ = "calculation_trajectory_link"
    __table_args__ = (
        Index("ix_calculation_trajectory_link_calculation_id", "calculation_id"),
    )

    trajectory_id: int | None = Field(
        default=None,
        foreign_key="trajectory.id",
        ondelete="CASCADE",
        nullable=False,
        primary_key=True,
    )
    calculation_id: int | None = Field(
        default=None,
        foreign_key="calculation.id",
        ondelete="CASCADE",
        nullable=False,
        primary_key=True,
    )
    role: Role = Field(
        sa_column=Column(Enum(Role, values_callable=lambda x: [e.value for e in x]))
    )

    trajectory: "TrajectoryRow" = Relationship(back_populates="calculation_links")
    calculation: "CalculationRow" = Relationship(back_populates="trajectory_links")
