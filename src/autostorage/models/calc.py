"""Calculation-related row definitions: model, calculation, validation."""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlmodel import (
    JSON,
    Column,
    Enum,
    Field,
    Index,
    Relationship,
    SQLModel,
    UniqueConstraint,
    func,
    text,
)

from autostorage.types import CalcStatus, CalcType, Role, _fk_field

from .link import StepValidationLink

if TYPE_CHECKING:
    from .geom import GeometryRow
    from .link import CalculationGeometryLink, CalculationTrajectoryLink
    from .rxn import StepRow
    from .traj import TrajectoryRow


# Calculation rows
class ModelRow(SQLModel, table=True):
    """Calculation model specification.

    Attributes
    ----------
    program
        Quantum chemistry program used (psi4, ORCA, ...)
    program_version
        Quantum chemistry program version.
    method
        Computational method (B3LYP, MP2, ...)
    basis
        Orbital basis set.
    """

    __tablename__ = "model"
    __table_args__ = (
        UniqueConstraint(
            "program",
            "program_version",
            "method",
            "basis",
            name="unique_model",
        ),
        # `unique_model` doesn't catch duplicates when `program_version` or `basis`
        # is NULL, since SQL treats NULL as distinct from itself in unique
        # constraints. This expression index closes that gap at the DB level.
        Index(
            "unique_model_null_safe",
            "program",
            text("coalesce(program_version, '')"),
            "method",
            text("coalesce(basis, '')"),
            unique=True,
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    program: str
    program_version: str | None = None
    method: str
    basis: str | None = None


class CalculationRow(SQLModel, table=True):
    """Quantum chemistry calculation and its associated data.

    Attributes
    ----------
    model_id
        Foreign key to the model used for this calculation.
    calc_type
        Type of calculation performed.
    status
        Lifecycle status of this calculation.
    error_message
        Error message recorded for a failed calculation, if any.
    input_provenance
        Metadata describing how the input was generated.
    output_provenance
        Metadata describing how the output was produced.
    model
        Model used for this calculation.
    geometry_links
        Raw link rows connecting geometries to this calculation.
    trajectory_links
        Raw link rows connecting trajectories to this calculation.
    """

    __tablename__ = "calculation"

    id: int | None = Field(default=None, primary_key=True)
    model_id: int | None = Field(
        default=None,
        foreign_key="model.id",
        ondelete="CASCADE",
        nullable=False,
        index=True,
    )
    calc_type: CalcType = Field(
        sa_column=Column(Enum(CalcType, values_callable=lambda x: [e.value for e in x]))
    )
    status: CalcStatus = Field(
        default=CalcStatus.PENDING,
        sa_column=Column(
            Enum(CalcStatus, values_callable=lambda x: [e.value for e in x])
        ),
    )
    input_provenance: dict[str, Any] | None = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    output_provenance: dict[str, Any] | None = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    created: datetime | None = Field(
        default=None,
        nullable=False,
        sa_column_kwargs={"server_default": func.now()},
    )
    error_message: str | None = Field(default=None)

    model: "ModelRow" = Relationship()
    geometry_links: list["CalculationGeometryLink"] = Relationship(
        back_populates="calculation"
    )
    trajectory_links: list["CalculationTrajectoryLink"] = Relationship(
        back_populates="calculation"
    )

    @property
    def input_geometries(self) -> list["GeometryRow"]:
        """Geometries linked to this calculation with an INPUT role."""
        return [
            link.geometry for link in self.geometry_links if link.role == Role.INPUT
        ]

    @property
    def output_geometries(self) -> list["GeometryRow"]:
        """Geometries linked to this calculation with an OUTPUT role."""
        return [
            link.geometry for link in self.geometry_links if link.role == Role.OUTPUT
        ]

    @property
    def input_trajectories(self) -> list["TrajectoryRow"]:
        """Trajectories linked to this calculation with an INPUT role."""
        return [
            link.trajectory for link in self.trajectory_links if link.role == Role.INPUT
        ]

    @property
    def output_trajectories(self) -> list["TrajectoryRow"]:
        """Trajectories linked to this calculation with an OUTPUT role."""
        return [
            link.trajectory
            for link in self.trajectory_links
            if link.role == Role.OUTPUT
        ]


class ValidationRow(SQLModel, table=True):
    """Validation result for a specific step and calculation.

    Attributes
    ----------
    calculation_id
        Foreign key to the calculation that performed this validation.
    method
        Type of validation step (e.g., ``irc``)
    extras
        Additional metadata attached to this validation.
    calculation
        Calculation that performed this validation.
    step
        Reaction step this validation belongs to.
    """

    __tablename__ = "validation"

    id: int | None = Field(default=None, primary_key=True)
    calculation_id: int | None = _fk_field("calculation.id")

    method: str
    # Intentionally unbounded free-form JSON; add a size/schema guardrail if
    # this is ever populated from a less-trusted input path.
    extras: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    calculation: "CalculationRow" = Relationship()
    step: "StepRow" = Relationship(
        back_populates="validations", link_model=StepValidationLink
    )
