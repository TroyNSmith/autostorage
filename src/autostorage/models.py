"""Database models."""

import operator
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Self, TypeVar, cast

import numpy as np
from automatics import Geometry, Identity, Model
from automatics.utils.exc import XYZFormatError
from automatics.utils.types import FloatArray
from automol import geom
from pydantic import BaseModel
from sqlalchemy import String
from sqlmodel import (
    JSON,
    CheckConstraint,
    Column,
    Field,
    Relationship,
    Session,
    SQLModel,
)

from .utils.exc import ShapeMismatchError
from .utils.misc import make_fields_optional
from .utils.types import FloatArrayTypeDecorator


# Base model & mixins
class PartialMixin:
    """Mixin for Partial method on SQLModel classes."""

    @classmethod
    def partial(cls: type[SQLModel], **attrs: Any) -> Self:  # noqa: ANN401
        """Return the model with partial assignment of required fields."""
        optional_model = make_fields_optional(cls)
        # Check valid fields
        invalid = set(attrs) - set(cls.model_fields)

        if invalid:
            msg = f" Unexpected fields in {cls.__name__}.partial(): {sorted(invalid)}"
            raise ValueError(msg)
        validated = optional_model(**attrs)

        data = validated.model_dump(
            exclude_unset=True,
        )

        return cast(
            "Self",
            cls.model_construct(_fields_set=set(attrs.keys()), **data),
        )


class ComparisonMixin(BaseModel):  # noqa: PLW1641
    """Mixin for defining Comparison behavior on SQLModel classes."""

    _field_comparisons: ClassVar[dict[str, Callable[[Any, Any], bool]] | None] = None

    def __eq__(self, other: object) -> bool:
        """Compare equivalency between self and other."""
        comps = self.__class__._field_comparisons or {}
        comps["id"] = comps.get("id", lambda _, __: True)

        if type(self) is not type(other):
            return False

        for field in type(self).model_fields:
            val_self = getattr(self, field, None)
            val_other = getattr(other, field, None)

            comp = comps.get(field, operator.eq)

            if not comp(val_self, val_other):
                return False

        return True


class SessionMixin(BaseModel):
    """Mixin for database session operations."""

    def add(self, sess: Session) -> Self:
        """Add database model to session."""
        sess.add(self)
        return self


class BaseRow(SQLModel, PartialMixin, ComparisonMixin):
    """Base model for AutoStorage SQL rows."""


BaseRowT = TypeVar("BaseRowT", bound=BaseRow)


# Link tables
class StationaryIdentityLink(BaseRow, table=True):
    """Association table linking stationary points to chemical identities.

    Attributes
    ----------
    stationary_id : int
        Foreign key to the linked stationary point.
    identity_id : int
        Foreign key to the linked identity.
    """

    __tablename__ = "stationary_identity_link"

    stationary_id: int = Field(
        foreign_key="stationary_point.id", primary_key=True, ondelete="CASCADE"
    )
    identity_id: int = Field(
        foreign_key="stationary_identity.id", primary_key=True, ondelete="CASCADE"
    )


class StationaryStageLink(BaseRow, table=True):
    """Association table linking stationary points to reaction stages.

    Attributes
    ----------
    stationary_id : int
        Foreign key to the linked stationary point.
    stage_id : int
        Foreign key to the linked reaction stage.
    """

    __tablename__ = "stationary_stage_link"

    stationary_id: int = Field(
        foreign_key="stationary_point.id", primary_key=True, ondelete="CASCADE"
    )
    stage_id: int = Field(foreign_key="stage.id", primary_key=True, ondelete="CASCADE")


class StepValidationLink(BaseRow, table=True):
    """Association table linking step validations to a reaction step.

    Attributes
    ----------
    reaction_step_id : int
        Foreign key to the linked step.
    validation_id : int
        Foreign key to the linked validation.
    step : StepRow
        The linked step.
    validation : ValidationRow
        The linked validation.
    """

    __tablename__ = "step_validation_link"

    reaction_step_id: int = Field(
        foreign_key="step.id", primary_key=True, ondelete="CASCADE"
    )
    validation_id: int = Field(
        foreign_key="step_validation.id", primary_key=True, ondelete="CASCADE"
    )


class TrajectoryGeometryLink(BaseRow, table=True):
    """Geometry and index along a trajectory.

    Attributes
    ----------
    geometry_id : int
        Foreign key to the linked geometry.
    trajectory_id : int
        Foreign key to the linked trajectory.
    index : list[int], optional
        Position of the geometry within the trajectory.
    geometry : GeometryRow
        The linked geometry.
    trajectory : TrajectoryRow
        The linked trajectory.
    """

    __tablename__ = "trajectory_step"

    id: int | None = Field(default=None, primary_key=True)

    geometry_id: int | None = Field(
        default=None,
        foreign_key="geometry.id",
        ondelete="CASCADE",
        nullable=False,
        index=True,
    )
    trajectory_id: int | None = Field(
        default=None,
        foreign_key="trajectory.id",
        ondelete="CASCADE",
        nullable=False,
        index=True,
    )

    index: list[int] | None = Field(default=None, sa_column=Column(JSON))

    geometry: "GeometryRow" = Relationship(back_populates="trajectory_steps")
    trajectory: "TrajectoryRow" = Relationship(back_populates="steps")


# Data tables
class EnergyRow(BaseRow, table=True):
    """Energy result for a specific geometry and calculation."""

    __tablename__ = "energy"
    id: int | None = Field(default=None, primary_key=True)

    geometry_id: int | None = Field(
        default=None, foreign_key="geometry.id", ondelete="CASCADE", nullable=False
    )
    calculation_id: int | None = Field(
        default=None, foreign_key="calculation.id", ondelete="CASCADE", nullable=False
    )

    value: float

    calculation: "CalculationRow" = Relationship(back_populates="energies")
    geometry: "GeometryRow" = Relationship(back_populates="energies")


class GradientRow(BaseRow, table=True):
    """Energy gradient result for a specific geometry and calculation."""

    __tablename__ = "gradient"
    id: int | None = Field(default=None, primary_key=True)

    geometry_id: int | None = Field(
        default=None, foreign_key="geometry.id", ondelete="CASCADE", nullable=False
    )
    calculation_id: int | None = Field(
        default=None, foreign_key="calculation.id", ondelete="CASCADE", nullable=False
    )

    value: list[float] = Field(sa_type=JSON)

    calculation: "CalculationRow" = Relationship(back_populates="gradients")
    geometry: "GeometryRow" = Relationship(back_populates="gradients")


class HessianRow(BaseRow, table=True):
    """Hessian result for a specific geometry and calculation."""

    __tablename__ = "hessian"
    id: int | None = Field(default=None, primary_key=True)

    geometry_id: int | None = Field(
        default=None, foreign_key="geometry.id", ondelete="CASCADE", nullable=False
    )
    calculation_id: int | None = Field(
        default=None, foreign_key="calculation.id", ondelete="CASCADE", nullable=False
    )

    value: list[list[float]] = Field(sa_type=JSON)

    calculation: "CalculationRow" = Relationship(back_populates="hessians")
    geometry: "GeometryRow" = Relationship(back_populates="hessians")

    @property
    def harmonic_frequencies(self) -> tuple[float, ...]:
        """Harmonic frequencies derived from the Hessian."""
        freqs, _ = geom.vibrational_analysis(geo=self.geometry, hess=self.value)
        return freqs


# Geometry table
class GeometryRow(BaseRow, Geometry, table=True):
    """Molecular geometry definition and metadata."""

    __tablename__ = "geometry"
    id: int | None = Field(default=None, primary_key=True)

    symbols: list[str] = Field(sa_column=Column(JSON))
    coordinates: FloatArray = Field(sa_column=Column(FloatArrayTypeDecorator))
    charge: int | None = Field(default=None, nullable=False)
    spin: int | None = Field(default=None, nullable=False)
    hash: str | None = Field(
        default=None,
        sa_column=Column(String(64), index=True, nullable=True, unique=True),
    )

    calculation_inputs: list["CalculationRow"] = Relationship(
        back_populates="input_geometry",
        sa_relationship_kwargs={"foreign_keys": "[CalculationRow.input_geometry_id]"},
    )
    calculation_outputs: list["CalculationRow"] = Relationship(
        back_populates="output_geometry",
        sa_relationship_kwargs={"foreign_keys": "[CalculationRow.output_geometry_id]"},
    )
    trajectory_steps: list["TrajectoryGeometryLink"] = Relationship(
        back_populates="geometry"
    )
    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="geometry"
    )
    energies: list["EnergyRow"] = Relationship(
        back_populates="geometry",
        sa_relationship_kwargs={"viewonly": True},
    )
    gradients: list["GradientRow"] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": lambda: GeometryRow.id == GradientRow.geometry_id,
            "foreign_keys": lambda: [GradientRow.geometry_id],
            "viewonly": True,
        }
    )
    hessians: list["HessianRow"] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": lambda: GeometryRow.id == HessianRow.geometry_id,
            "foreign_keys": lambda: [HessianRow.geometry_id],
            "viewonly": True,
        }
    )

    def attach_energy(self, *, calc: "CalculationRow", value: float) -> EnergyRow:
        """Attach energy to geometry.

        Parameters
        ----------
        calc
            Calculation instance producing the value.
        value
            Energy in Hartree.

        Returns
        -------
        EnergyRow
        """
        return EnergyRow(geometry=self, calculation=calc, value=value)

    def attach_gradient(
        self, calc: "CalculationRow", value: list[float]
    ) -> GradientRow:
        """Attach energy gradient to geometry.

        Parameters
        ----------
        calc
            Calculation instance producing the value.
        value
            Gradient in Hartree/Bohr.

        Returns
        -------
        GradientRow
        """
        exp_shape = (3 * self.atom_count,)
        val_shape = np.shape(value)

        if val_shape != exp_shape:
            msg = f"Expected {exp_shape} gradient, got {val_shape}."
            raise ShapeMismatchError(msg)

        return GradientRow(geometry=self, calculation=calc, value=value)

    def attach_hessian(
        self, calc: "CalculationRow", value: list[list[float]]
    ) -> HessianRow:
        """Attach Hessian to geometry.

        Parameters
        ----------
        calc
            Calculation instance producing the value.
        value
            Hessian values in Hartree/Bohr**2.

        Returns
        -------
        HessianRow
        """
        exp_shape = (3 * self.atom_count, 3 * self.atom_count)
        val_shape = np.shape(value)

        if val_shape != exp_shape:
            msg = f"Expected {exp_shape} Hessian, got {val_shape}."
            raise ShapeMismatchError(msg)

        return HessianRow(geometry=self, calculation=calc, value=value)


# Trajectory table
class TrajectoryRow(BaseRow, table=True):
    """Ordered sequence of geometries from a calculation trajectory.

    Attributes
    ----------
    id : int, optional
        Primary key.
    ndim : int, optional
        Dimensionality of the trajectory index (e.g. 1 for a linear scan).
    geometries : list[GeometryRow]
        Ordered list of geometries in this trajectory.
    steps : list[TrajectoryStepRow]
        Raw link rows connecting geometries to this trajectory.
    calculation_inputs : list[CalculationRow]
        Calculations that used this trajectory as input.
    calculation_outputs : list[CalculationRow]
        Calculations that produced this trajectory.
    """

    __tablename__ = "trajectory"
    id: int | None = Field(default=None, primary_key=True)

    calculation_inputs: list["CalculationRow"] = Relationship(
        back_populates="input_trajectory",
        sa_relationship_kwargs={"foreign_keys": "[CalculationRow.input_trajectory_id]"},
    )
    calculation_outputs: list["CalculationRow"] = Relationship(
        back_populates="output_trajectory",
        sa_relationship_kwargs={
            "foreign_keys": "[CalculationRow.output_trajectory_id]"
        },
    )
    steps: list[TrajectoryGeometryLink] = Relationship(back_populates="trajectory")

    @property
    def step_count(self) -> int:
        """Return number of steps in trajectory."""
        return len(self.steps)

    @property
    def geometry_hashes(self) -> list[str]:
        """Return all geometry hashes in trajectory."""
        return [g.hash or geom.geometry_hash(g) for g in self.geometries]

    @property
    def indices(self) -> list[list[int]] | None:
        """Return indices from steps, if present."""
        idxs = [s.index for s in self.steps if s.index is not None]
        return idxs or None

    @indices.setter
    def indices(self, value: list[list[int]] | None) -> None:
        """Set or clear indices across all steps."""
        if value is None:
            for step in self.steps:
                step.index = None
            return

        for step, idx in zip(self.steps, value, strict=True):
            step.index = idx

    @property
    def geometries(self) -> list[GeometryRow]:
        """Return geometries from steps."""
        if any(s.index is None for s in self.steps):
            return [s.geometry for s in self.steps]

        return [s.geometry for s in sorted(self.steps, key=lambda s: s.index)]

    @geometries.setter
    def geometries(self, value: list[GeometryRow]) -> None:
        """Set geometries across all steps."""
        if any(s.index is None for s in self.steps):
            for step, geo in zip(self.steps, value, strict=True):
                step.geometry = geo
            return
        # Match geometry getter sorting behavior if indices are present
        sorted_steps = sorted(self.steps, key=lambda s: s.index)
        for step, geo in zip(sorted_steps, value, strict=True):
            step.geometry = geo

    def xyz_block(self, comments: list[str | None] | None = None) -> str:
        """Return xyz block representation of trajectory.

        Parameters
        ----------
        comments
            List of comments to write with the geometries in the order of their index.
            *Shape must match the number of geometries being written.*

        Returns
        -------
        xyz block
        """
        if comments is not None and len(comments) != len(self.steps):
            msg = (
                f"Number of comments provided ({len(comments)}) does not match number"
                f"of trajectory steps ({len(self.steps)})."
            )
            raise ValueError(msg)

        blocks = []
        for i, step in enumerate(
            sorted(self.steps, key=lambda s: s.index) if self.indices else self.steps
        ):
            if comments and comments[i] is not None:
                comment = str(comments[i]).strip()
            elif step.index is not None:
                comment = str(step.index)
            else:
                comment = ""

            blocks.append(step.geometry.xyz_block(comment=comment))

        return "\n".join(blocks)

    @classmethod
    def from_xyz_block(
        cls,
        xyz_block: str,
        *,
        indices: list[list[int]] | None = None,
        charge: int | None = None,
        spin: int | None = None,
    ) -> Self:
        """Instantiate TrajectoryRow from xyz block format.

        Parameters
        ----------
        xyz_block
            xyz formatted string
        indices
            List of indices to assign trajectory steps in the order they are read.
            *Length must match the number of geometries being read.*
        charge
            Charge to assign to resulting geometries.
        spin
            Spin to assign to resulting geometries

        Returns
        -------
        TrajectoryRow
        """
        lines = xyz_block.splitlines()
        if not lines:
            msg = "The provided xyz block is empty."
            raise XYZFormatError(msg)

        steps: list[TrajectoryGeometryLink] = []
        line_idx = 0
        total_lines = len(lines)

        while line_idx < total_lines:
            try:
                natoms = int(lines[line_idx])
            except ValueError as e:
                msg = (
                    f"Expected number of atoms at line {line_idx},"
                    f"found `{lines[line_idx]}`"
                )
                raise XYZFormatError(msg) from e

            block_size = natoms + 2
            if line_idx + block_size > total_lines:
                msg = (
                    f"Incomplete xyz block starting at {line_idx}. Expected"
                    f"{block_size} lines but only {total_lines - line_idx} remain."
                )
                raise XYZFormatError(msg)

            block = "\n".join(lines[line_idx : line_idx + block_size])
            geo = GeometryRow.from_xyz_block(block, charge=charge, spin=spin)

            step_idx = indices[len(steps)] if indices else None
            steps.append(TrajectoryGeometryLink(index=step_idx, geometry=geo))

            line_idx += block_size

        if indices and len(indices) != len(steps):
            msg = (
                f"Number of indices provided ({len(indices)}) does not match number of"
                f"parsed trajectory steps ({len(steps)})."
            )
            raise ValueError(msg)

        return cls(steps=steps)

    def xyz_file(
        self, path: str | Path, *, comments: list[str | None] | None = None
    ) -> None:
        """Instantiate TrajectoryRow from xyz format file.

        Parameters
        ----------
        path
            Path to an xyz file.
        comments
            List of comments to write with the geometries in the order of their index.
            *Shape must match the number of geometries being written.*
        """
        Path(path).write_text(self.xyz_block(comments=comments))

    @classmethod
    def from_xyz_file(
        cls,
        path: str | Path,
        *,
        indices: list[list[int]] | None = None,
        charge: int | None = None,
        spin: int | None = None,
    ) -> Self:
        """Instantiate TrajectoryRow from xyz format file.

        Parameters
        ----------
        path
            Path to an xyz file.
        indices
            List of indices to assign trajectory steps in the order they are read.
            *Shape must match the number of geometries being read.*
        charge
            Charge to assign to resulting geometries.
        spin
            Spin to assign to resulting geometries

        Returns
        -------
        TrajectoryRow
        """
        return cls.from_xyz_block(
            Path(path).read_text(), indices=indices, charge=charge, spin=spin
        )


# Calculation tables
class ModelRow(BaseRow, Model, table=True):
    """Quantum chemistry program and method parameters."""

    __tablename__ = "model"
    id: int | None = Field(default=None, primary_key=True)

    hash: str | None = Field(
        default=None,
        sa_column=Column(String(64), index=True, nullable=True, unique=True),
    )

    calculations: list["CalculationRow"] = Relationship(back_populates="model")


class CalculationRow(BaseRow, table=True):
    """A single quantum chemistry calculation and its associated data."""

    __tablename__ = "calculation"
    id: int | None = Field(default=None, primary_key=True)

    model_id: int | None = Field(
        default=None, foreign_key="model.id", ondelete="CASCADE", nullable=False
    )
    calc_type: str = Field(sa_column=Column(String))
    input_geometry_id: int | None = Field(
        default=None, foreign_key="geometry.id", ondelete="CASCADE"
    )
    output_geometry_id: int | None = Field(
        default=None, foreign_key="geometry.id", ondelete="CASCADE"
    )
    input_trajectory_id: int | None = Field(
        default=None, foreign_key="trajectory.id", ondelete="CASCADE"
    )
    output_trajectory_id: int | None = Field(
        default=None, foreign_key="trajectory.id", ondelete="CASCADE"
    )

    input_provenance: dict[str, Any] | None = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    output_provenance: dict[str, Any] | None = Field(
        default_factory=dict, sa_column=Column(JSON)
    )

    model: "ModelRow" = Relationship(back_populates="calculations")
    input_geometry: "GeometryRow" = Relationship(
        back_populates="calculation_inputs",
        sa_relationship_kwargs={"foreign_keys": "[CalculationRow.input_geometry_id]"},
    )
    output_geometry: "GeometryRow" = Relationship(
        back_populates="calculation_outputs",
        sa_relationship_kwargs={"foreign_keys": "[CalculationRow.output_geometry_id]"},
    )
    input_trajectory: "TrajectoryRow" = Relationship(
        back_populates="calculation_inputs",
        sa_relationship_kwargs={"foreign_keys": "[CalculationRow.input_trajectory_id]"},
    )
    output_trajectory: "TrajectoryRow" = Relationship(
        back_populates="calculation_outputs",
        sa_relationship_kwargs={
            "foreign_keys": "[CalculationRow.output_trajectory_id]"
        },
    )
    energies: list["EnergyRow"] = Relationship(
        back_populates="calculation", cascade_delete=True
    )
    gradients: list["GradientRow"] = Relationship(
        back_populates="calculation", cascade_delete=True
    )
    hessians: list["HessianRow"] = Relationship(
        back_populates="calculation", cascade_delete=True
    )
    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="calculation"
    )
    validations: list["StepValidationRow"] = Relationship(back_populates="calculation")


class StepValidationRow(BaseRow, table=True):
    """Validation result for a specific step and calculation."""

    __tablename__ = "step_validation"
    id: int | None = Field(default=None, primary_key=True)

    calculation_id: int | None = Field(
        default=None, foreign_key="calculation.id", ondelete="CASCADE"
    )

    method: str
    extras: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    calculation: "CalculationRow" = Relationship(back_populates="validations")
    step: "StepRow" = Relationship(
        back_populates="validations", link_model=StepValidationLink
    )


# Stationary point tables
class StationaryPointRow(BaseRow, table=True):
    """A stationary point on a potential energy surface.

    Attributes
    ----------
    geometry_id : int
        Foreign key to the underlying molecular geometry.
    calculation_id : int
        Foreign key to the calculation that identified this point.
    order : int
        Hessian index (0 for minima, 1 for first-order saddle points).
    is_pseudo : bool
        Whether this point is not a true stationary point (e.g. constrained).
    geometry : GeometryRow
        Geometry defining the coordinates of this point.
    calculation : CalculationRow
        Calculation that identified this point.
    identities : list[IdentityRow]
        Chemical identifiers (e.g. InChI, SMILES) for this point.
    stages : list[StageRow]
        Reaction stages this stationary point belongs to.
    """

    __tablename__ = "stationary_point"
    id: int | None = Field(default=None, primary_key=True)

    geometry_id: int | None = Field(
        default=None, foreign_key="geometry.id", ondelete="CASCADE", nullable=False
    )
    calculation_id: int | None = Field(
        default=None, foreign_key="calculation.id", ondelete="CASCADE", nullable=False
    )

    order: int = 0
    is_pseudo: bool = False
    is_valid: bool = False

    geometry: "GeometryRow" = Relationship(back_populates="stationary_points")
    calculation: "CalculationRow" = Relationship(back_populates="stationary_points")

    identities: list["IdentityRow"] = Relationship(
        back_populates="stationary_points", link_model=StationaryIdentityLink
    )
    stages: list["StageRow"] = Relationship(
        back_populates="stationary_points", link_model=StationaryStageLink
    )

    energies: list["EnergyRow"] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": lambda: (
                StationaryPointRow.geometry_id == EnergyRow.geometry_id
            ),
            "foreign_keys": lambda: [EnergyRow.geometry_id],
            "viewonly": True,
        }
    )
    gradients: list["GradientRow"] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": lambda: (
                StationaryPointRow.geometry_id == GradientRow.geometry_id
            ),
            "foreign_keys": lambda: [GradientRow.geometry_id],
            "viewonly": True,
        }
    )
    hessians: list["HessianRow"] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": lambda: (
                StationaryPointRow.geometry_id == HessianRow.geometry_id
            ),
            "foreign_keys": lambda: [HessianRow.geometry_id],
            "viewonly": True,
        }
    )


class IdentityRow(BaseRow, Identity, table=True):
    """A chemical identifier associated with one or more stationary points.

    Attributes
    ----------
    kind : str
        Category of identifier (e.g. ``stereoisomer``, ``formula``).
    algorithm : str
        Method used to generate the identifier (e.g. ``rdkit inchi``, ``rdkit smiles``).
    value : str
        The resulting identifier string.
    stationary_points : list[StationaryPointRow]
        Stationary points sharing this identity.
    identity_extras : list[IdentityExtraRow]
        Additional key-value metadata attached to this identity.
    """

    __tablename__ = "stationary_identity"
    id: int | None = Field(default=None, primary_key=True)

    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="identities", link_model=StationaryIdentityLink
    )
    identity_extras: list["IdentityExtraRow"] = Relationship(back_populates="identity")


class IdentityExtraRow(BaseRow, table=True):
    """Additional key-value metadata attached to a chemical identity.

    Attributes
    ----------
    identity_id : int
        Foreign key to the parent identity.
    attribute : str
        Name of the extra attribute.
    value : str
        Value of the extra attribute.
    identity : IdentityRow
        The parent identity this extra belongs to.
    """

    __tablename__ = "stationary_identity_extra"
    id: int | None = Field(default=None, primary_key=True)

    identity_id: int | None = Field(
        default=None,
        foreign_key="stationary_identity.id",
        ondelete="CASCADE",
        nullable=False,
    )

    attribute: str
    value: str

    identity: "IdentityRow" = Relationship(back_populates="identity_extras")


# Reaction tables
class StageRow(BaseRow, table=True):
    """A chemical state (reactant, product, or transition state) in a reaction.

    Attributes
    ----------
    is_ts : bool
        Whether this stage represents a transition state.
    backward_steps : list[StepRow]
        Elementary steps where this stage is the reactant.
    transition_steps : list[StepRow]
        Elementary steps where this stage is the transition state.
    forward_steps : list[StepRow]
        Elementary steps where this stage is the product.
    stationary_points : list[StationaryPointRow]
        Stationary point geometries mapped to this stage.
    """

    __tablename__ = "stage"
    id: int | None = Field(default=None, primary_key=True)

    is_ts: bool = False

    backward_steps: list["StepRow"] = Relationship(
        back_populates="stage1",
        sa_relationship_kwargs={"foreign_keys": "[StepRow.stage1_id]"},
    )
    transition_steps: list["StepRow"] = Relationship(
        back_populates="ts_stage",
        sa_relationship_kwargs={"foreign_keys": "[StepRow.ts_stage_id]"},
    )
    forward_steps: list["StepRow"] = Relationship(
        back_populates="stage2",
        sa_relationship_kwargs={"foreign_keys": "[StepRow.stage2_id]"},
    )
    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="stages", link_model=StationaryStageLink
    )


class StepRow(BaseRow, table=True):
    """An elementary reaction step connecting a reactant, transition state, and product.

    Attributes
    ----------
    stage1_id : int
        Foreign key to the reactant stage.
    ts_stage_id : int
        Foreign key to the transition state stage.
    stage2_id : int, optional
        Foreign key to the product stage.
    is_barrierless : bool
        Whether this step proceeds without a formal transition state.
    stage1 : StageRow
        The reactant stage for this step.
    ts_stage : StageRow
        The transition state stage for this step.
    stage2 : StageRow, optional
        The product stage for this step.
    """

    __tablename__ = "step"
    __table_args__ = (
        CheckConstraint(
            "(is_barrierless = TRUE AND ts_stage_id IS NULL) OR "
            "(is_barrierless = FALSE AND ts_stage_id IS NOT NULL)",
            name="check_barrierless_or_transition",
        ),
    )
    id: int | None = Field(default=None, primary_key=True)

    stage1_id: int | None = Field(
        default=None, foreign_key="stage.id", index=True, nullable=False
    )
    ts_stage_id: int | None = Field(default=None, foreign_key="stage.id", index=True)
    stage2_id: int | None = Field(
        default=None, foreign_key="stage.id", index=True, nullable=True
    )
    is_barrierless: bool = False

    stage1: "StageRow" = Relationship(
        back_populates="backward_steps",
        sa_relationship_kwargs={"foreign_keys": "[StepRow.stage1_id]"},
    )
    ts_stage: "StageRow" = Relationship(
        back_populates="transition_steps",
        sa_relationship_kwargs={"foreign_keys": "[StepRow.ts_stage_id]"},
    )
    stage2: "StageRow" = Relationship(
        back_populates="forward_steps",
        sa_relationship_kwargs={"foreign_keys": "[StepRow.stage2_id]"},
    )
    validations: list["StepValidationRow"] = Relationship(
        back_populates="step", link_model=StepValidationLink
    )


# Type hinting
if TYPE_CHECKING:

    class GeometryRow:
        """Molecular geometry definition and metadata."""

        def __init__(
            self,
            *,
            symbols: list[str],
            coordinates: list[list[float]] | FloatArray,
            charge: int = 0,
            spin: int = 0,
        ) -> None:
            """Molecular geometry definition and metadata.

            Parameters
            ----------
            symbols

            coordinates

            charge

            spin
            """
