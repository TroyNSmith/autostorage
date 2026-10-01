"""SQLModel row definitions for autostorage's schema."""

import uuid
from collections.abc import Sequence
from typing import Any, Self

from automol import Geometry, IdentityKind
from automol.utils.types import CoordinatesField
from sqlmodel import (
    JSON,
    CheckConstraint,
    Column,
    Enum,
    Field,
    Index,
    Relationship,
    SQLModel,
    UniqueConstraint,
    text,
)
from sqlmodel.main import SQLModelConfig

from .types import (
    CompressedArrayTypeDecorator,
    Role,
    _fk_field,
)


# 0. Link rows
# NOTE: Link tables are named by the two entities they connect, in alphabetical order.
class CalculationGeometryLink(SQLModel, table=True):
    """Association table linking geometries to a calculation."""

    __tablename__ = "calculation_geometry_link"
    __table_args__ = (
        # The composite primary key only serves lookups keyed by `geometry_id`
        # (its leading column); this adds a matching index for `calculation_id`.
        Index("ix_calculation_geometry_link_calculation_id", "calculation_id"),
    )

    geometry_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="geometry.id",
        ondelete="CASCADE",
        nullable=False,
        primary_key=True,
    )
    """Foreign key to the linked `GeometryRow`."""
    calculation_id: int | None = Field(
        default=None,
        foreign_key="calculation.id",
        ondelete="CASCADE",
        nullable=False,
        primary_key=True,
    )
    """Foreign key to the linked `CalculationRow`."""
    role: Role = Field(
        sa_column=Column(Enum(Role, values_callable=lambda x: [e.value for e in x]))
    )
    """Role the `GeometryRow` plays for `CalculationRow` (input/output)."""
    geometry: "GeometryRow" = Relationship(back_populates="calculation_links")
    """The linked `GeometryRow`."""
    calculation: "CalculationRow" = Relationship(back_populates="geometry_links")
    """The linked `CalculationRow`."""


class GeometryTrajectoryLink(SQLModel, table=True):
    """Association table linking geometries to a trajectory."""

    __tablename__ = "geometry_trajectory_link"
    __table_args__ = (
        Index("ix_geometry_trajectory_link_trajectory_id", "trajectory_id"),
    )

    geometry_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="geometry.id",
        primary_key=True,
        ondelete="CASCADE",
        nullable=False,
    )
    """Foreign key to the linked `GeometryRow`."""
    trajectory_id: int | None = Field(
        default=None,
        foreign_key="trajectory.id",
        primary_key=True,
        ondelete="CASCADE",
        nullable=False,
    )
    """Foreign key to the linked `TrajectoryRow`."""
    index: list[int] | None = Field(default=None, sa_column=Column(JSON))
    """Position of `geometry` within the `trajectory`."""
    geometry: "GeometryRow" = Relationship(back_populates="trajectory_links")
    """The linked `GeometryRow`."""
    trajectory: "TrajectoryRow" = Relationship(back_populates="geometry_links")
    """The linked `TrajectoryRow`."""


class CalculationTrajectoryLink(SQLModel, table=True):
    """Association table linking trajectories to a calculation.

    Attributes:
        trajectory_id: Foreign key to the linked trajectory.
        calculation_id: Foreign key to the linked calculation.
        role: Role the trajectory plays for this calculation (input/output).
        trajectory: The linked trajectory (back-populated from
            `TrajectoryRow.calculation_links`).
        calculation: The linked calculation (back-populated from
            `CalculationRow.trajectory_links`).
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


class StageStationaryLink(SQLModel, table=True):
    """Association table linking stationary points to reaction stages.

    Attributes:
        stationary_id: Foreign key to the linked stationary point.
        stage_id: Foreign key to the linked reaction stage.
    """

    __tablename__ = "stage_stationary_link"
    __table_args__ = (Index("ix_stage_stationary_link_stage_id", "stage_id"),)

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


class StepValidationLink(SQLModel, table=True):
    """Association table linking validations to a step.

    Attributes:
        step_id: Foreign key to the linked step.
        validation_id: Foreign key to the linked validation.

    Note:
        Relationships are managed bidirectionally via `ValidationRow.step` and
        `StepRow.validations` using this table's `link_model`.
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


class IdentityStationaryLink(SQLModel, table=True):
    """Association table linking chemical identities to stationary points.

    Attributes:
        stationary_id: Foreign key to the linked stationary point.
        identity_id: Foreign key to the linked chemical identity.

    Note:
        Relationships are managed bidirectionally via `StationaryPointRow.identities`
        and `IdentityRow.stationary_points` using this table's `link_model`.
    """

    __tablename__ = "identity_stationary_link"
    __table_args__ = (Index("ix_identity_stationary_link_identity_id", "identity_id"),)

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


# 1. Existential data rows
class GeometryRow(SQLModel, Geometry, table=True):
    """Molecular geometry definition and metadata.

    Attributes:
        id: Primary key.
        symbols: Atomic symbols in order.
        coordinates: Atomic coordinates in Angstrom. A `pint.Quantity` with length units
            is converted to Angstrom.
        charge: Total molecular charge.
        spin: Number of unpaired electrons (2S).
        properties: Property values (energies, gradients, Hessians, ...) computed at
            this geometry.
        stationary_points: Stationary points defined by this geometry.
        trajectory_links: Raw link rows connecting this geometry to trajectories.
        calculation_links: Raw link rows connecting this geometry to calculations.
    """

    __tablename__ = "geometry"
    model_config = SQLModelConfig(arbitrary_types_allowed=True)

    id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)
    symbols: list[str] = Field(sa_column=Column(JSON))
    coordinates: CoordinatesField = Field(
        sa_column=Column(CompressedArrayTypeDecorator())
    )
    charge: int = 0
    spin: int = 0

    properties: list["PropertyValueRow"] = Relationship(back_populates="geometry")
    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="geometry"
    )
    trajectory_links: list["GeometryTrajectoryLink"] = Relationship(
        back_populates="geometry"
    )
    calculation_links: list["CalculationGeometryLink"] = Relationship(
        back_populates="geometry"
    )

    def relabel_atoms(self, indices: Sequence[int]) -> Self:
        """Return a reordered copy of this geometry as a new, unsaved row.

        Unlike `automol.Geometry.relabel_atoms`, the copy gets a fresh `id` and
        no relationships, so that it can be added to a session as a new row.
        """
        relabeled = super().relabel_atoms(indices)
        return type(self)(
            **{name: getattr(relabeled, name) for name in Geometry.model_fields}
        )


class TrajectoryRow(SQLModel, table=True):
    """Ordered sequence of geometries from a calculation trajectory.

    Attributes:
        id: Primary key.
        geometry_links: Raw link rows connecting geometries to this trajectory.
        calculation_links: Raw link rows connecting calculations to this trajectory.
    """

    __tablename__ = "trajectory"

    id: int | None = Field(default=None, primary_key=True)
    ndim: int | None = Field(default=None, nullable=True)

    geometry_links: list["GeometryTrajectoryLink"] = Relationship(
        back_populates="trajectory"
    )
    calculation_links: list["CalculationTrajectoryLink"] = Relationship(
        back_populates="trajectory"
    )


class ModelRow(SQLModel, table=True):
    """Calculation model specification.

    Attributes:
        id: Primary key.
        program: Quantum chemistry program used (psi4, ORCA, ...)
        program_version: Quantum chemistry program version.
        method: Computational method (B3LYP, MP2, ...)
        basis: Orbital basis set.
        keywords: Additional keywords and options for the calculation.
        calculations: Calculations performed using this model.
    """

    __tablename__ = "model"

    id: int | None = Field(default=None, primary_key=True)
    program: str
    program_version: str | None = None
    method: str
    basis: str | None = None
    keywords: dict[str, Any] | None = Field(
        default_factory=dict, sa_column=Column(JSON)
    )

    calculations: list["CalculationRow"] = Relationship(back_populates="model")


class CalculationRow(SQLModel, table=True):
    """Quantum chemistry calculation and its associated data.

    Attributes:
        id: Primary key.
        model_id: Foreign key to the model used for this calculation.
        calc_type: Type of calculation (energy, gradient, hessian, etc.).
        input_provenance: Metadata describing how the input was generated.
        output_provenance: Metadata describing how the output was produced.
        model: Model used for this calculation.
        geometry_links: Raw link rows connecting geometries to this calculation.
        trajectory_links: Raw link rows connecting trajectories to this calculation.
        properties: Property values (energies, gradients, Hessians, ...) produced by
            this calculation.
        validations: Validation results performed by this calculation.
        stationary_points: Stationary points identified by this calculation.
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
    calc_type: str
    input_provenance: dict[str, Any] | None = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    output_provenance: dict[str, Any] | None = Field(
        default_factory=dict, sa_column=Column(JSON)
    )

    model: "ModelRow" = Relationship(back_populates="calculations")
    properties: list["PropertyValueRow"] = Relationship(back_populates="calculation")
    validations: list["ValidationRow"] = Relationship(back_populates="calculation")
    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="calculation"
    )
    geometry_links: list["CalculationGeometryLink"] = Relationship(
        back_populates="calculation"
    )
    trajectory_links: list["CalculationTrajectoryLink"] = Relationship(
        back_populates="calculation"
    )


class PropertyKindRow(SQLModel, table=True):
    """A kind of property (e.g. ``energy``, ``gradient``, ``hessian``).

    Rows mirror the in-memory `autostorage.property.PropertyKindRegistry`, keyed
    by name. Validation and storage dtype are looked up from the registry by
    name, so rows loaded from the database behave the same as freshly seeded
    ones.
    """

    __tablename__ = "property_kind"

    name: str = Field(primary_key=True)
    """Primary key; name of the registered property kind."""
    property_values: list["PropertyValueRow"] = Relationship(
        back_populates="property_kind"
    )
    """The linked `PropertyValueRow`s."""


class PropertyValueRow(SQLModel, table=True):
    """Property value for a specific geometry and calculation."""

    __tablename__ = "property_value"
    model_config = SQLModelConfig(arbitrary_types_allowed=True)

    id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)
    """Primary key."""
    geometry_id: uuid.UUID | None = _fk_field("geometry.id")
    """Foreign key to the linked `GeometryRow`."""
    geometry: "GeometryRow" = Relationship(back_populates="properties")
    calculation_id: int | None = _fk_field("calculation.id")
    """Foreign key to the linked `CalculationRow`."""
    calculation: "CalculationRow" = Relationship(back_populates="properties")
    """The linked `CalculationRow`."""
    property_kind_name: str | None = _fk_field("property_kind.name")
    """Foreign key to the linked `PropertyKindRow` (e.g. ``"energy"``)."""
    property_kind: "PropertyKindRow" = Relationship(back_populates="property_values")
    """The linked `PropertyKindRow`."""
    value: Any = Field(sa_column=Column(CompressedArrayTypeDecorator(dtype=None)))
    """Value produced by `geometry` and `calculation`, as a NumPy array.

    Validated and cast to the property kind's dtype on flush (float64, except
    float32 for Hessians), so it may be assigned as a float, sequence, or array.
    """


class ValidationRow(SQLModel, table=True):
    """Validation result for a specific step and calculation.

    Attributes:
        id: Primary key.
        calculation_id: Foreign key to the calculation that performed this validation.
        method: Type of validation step (e.g., ``irc``)
        extras: Additional metadata attached to this validation.
        calculation: Calculation that performed this validation.
        step: Reaction step this validation belongs to.
    """

    __tablename__ = "validation"

    id: int | None = Field(default=None, primary_key=True)
    calculation_id: int | None = _fk_field("calculation.id")

    method: str
    extras: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    calculation: "CalculationRow" = Relationship(back_populates="validations")
    step: "StepRow" = Relationship(
        back_populates="validations", link_model=StepValidationLink
    )


# 2. Stationary point rows
class StationaryPointRow(SQLModel, table=True):
    """A stationary point on a potential energy surface.

    Attributes:
        id: Primary key.
        geometry_id: Foreign key to the underlying molecular geometry.
        calculation_id: Foreign key to the calculation that identified this point.
        order: Hessian index (0 for minima, 1 for first-order saddle points).
        is_pseudo: Whether this point is not a true stationary point (e.g. constrained).
        is_validated: Whether this stationary point has been validated (e.g., by Hessian
            calculation).
        geometry: Geometry defining the coordinates of this point.
        calculation: Calculation that identified this point.
        identities: Chemical identifiers (e.g. InChI, SMILES) for this point.
        stages: Reaction stages this stationary point belongs to.
    """

    __tablename__ = "stationary_point"

    id: int | None = Field(default=None, primary_key=True)
    geometry_id: uuid.UUID | None = _fk_field("geometry.id")
    calculation_id: int | None = _fk_field("calculation.id")
    order: int = 0
    is_pseudo: bool = False
    is_validated: bool = False

    geometry: "GeometryRow" = Relationship(back_populates="stationary_points")
    calculation: "CalculationRow" = Relationship(back_populates="stationary_points")
    identities: list["IdentityRow"] = Relationship(
        back_populates="stationary_points", link_model=IdentityStationaryLink
    )
    stages: list["StageRow"] = Relationship(
        back_populates="stationaries", link_model=StageStationaryLink
    )


# 3. Reaction network rows
class StageRow(SQLModel, table=True):
    """A chemical state (reactant, product, or transition state) in a reaction.

    Attributes:
        id: Primary key.
        is_ts: Whether this stage represents a transition state.
        stationaries: Stationary points that make up this stage (bidirectional via
            `link_model=StageStationaryLink`).
        steps: Reaction steps referencing this stage as `stage1`, `stage2`, or
            `stage_ts`. Read-only view derived from `StepRow`'s foreign keys;
            use `stage1`, `stage2`, `stage_ts` relationships on `StepRow` for
            writing.
    """

    __tablename__ = "stage"

    id: int | None = Field(default=None, primary_key=True)
    is_ts: bool = False

    stationaries: list["StationaryPointRow"] = Relationship(
        back_populates="stages", link_model=StageStationaryLink
    )
    steps: list["StepRow"] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "or_("
            "StageRow.id == StepRow.stage_id1, "
            "StageRow.id == StepRow.stage_id2, "
            "StageRow.id == StepRow.stage_id_ts"
            ")",
            "viewonly": True,
        }
    )


class StepRow(SQLModel, table=True):
    """An elementary reaction step connecting a reactant, TS, and product."""

    __tablename__ = "step"
    __table_args__ = (
        UniqueConstraint(
            "stage_id1", "stage_id2", "stage_id_ts", name="unq_step_stages"
        ),
        CheckConstraint("stage_id1 < stage_id2", name="chk_stage_order"),
        # `unq_step_stages` doesn't catch duplicate barrierless steps (stage_id_ts
        # NULL), since SQL never treats NULL as equal to itself in a unique
        # constraint. This expression index closes that gap at the DB level.
        Index(
            "unq_step_stages_null_safe",
            "stage_id1",
            "stage_id2",
            text("coalesce(stage_id_ts, 0)"),
            unique=True,
        ),
        # `stage_id1` is already covered as the leading column of the two indexes
        # above, but is indexed explicitly here too for symmetry/clarity.
        Index("ix_step_stage_id1", "stage_id1"),
        Index("ix_step_stage_id2", "stage_id2"),
        Index("ix_step_stage_id_ts", "stage_id_ts"),
    )

    id: int | None = Field(default=None, primary_key=True)
    """Primary key."""
    stage_id1: int | None = Field(
        default=None,
        foreign_key="stage.id",
        ondelete="CASCADE",
        nullable=False,
    )
    """The step's first non-TS stage (reactant or product)."""
    stage_id2: int | None = Field(
        default=None,
        foreign_key="stage.id",
        ondelete="CASCADE",
        nullable=False,
    )
    """The step's second non-TS stage (reactant or product)."""
    stage_id_ts: int | None = Field(
        default=None,
        foreign_key="stage.id",
        ondelete="CASCADE",
    )
    """The step's TS stage."""
    is_barrierless: bool = False
    """Whether this step proceeds without a formal TS."""
    validations: list["ValidationRow"] = Relationship(
        back_populates="step", link_model=StepValidationLink
    )
    """Validation calculations performed on `StepRow`."""
    stage1: "StageRow" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[StepRow.stage_id1]"}
    )
    """The step's first non-TS stage (reactant or product)."""
    stage2: "StageRow" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[StepRow.stage_id2]"}
    )
    """The step's second non-TS stage (reactant or product)."""
    stage_ts: "StageRow" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[StepRow.stage_id_ts]"}
    )
    """The step's TS stage, or `None` if barrierless."""


# 4. Identity rows
class IdentityAlgorithmRow(SQLModel, table=True):
    """A chemical identifier algorithm, mirroring an `automol.Algorithm`.

    Attributes:
        id: Primary key.
        name: Unique algorithm name (e.g. ``rdkit inchi``).
        kind: Category of identifier produced (e.g. ``stereoisomer``, ``formula``).
        parent_algorithm_id: Foreign key to the parent algorithm, whose identity
            disambiguates this one's `other_geos`, if any.
    """

    __tablename__ = "identity_algorithm"
    model_config = SQLModelConfig(arbitrary_types_allowed=True)

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True)
    kind: IdentityKind
    parent_algorithm_id: int | None = Field(
        default=None,
        foreign_key="identity_algorithm.id",
        ondelete="CASCADE",
        nullable=True,
    )

    parent_algorithm: "IdentityAlgorithmRow" = Relationship(
        sa_relationship_kwargs={
            "foreign_keys": "[IdentityAlgorithmRow.parent_algorithm_id]"
        }
    )
    identities: list["IdentityRow"] = Relationship(back_populates="algorithm")


class IdentityRow(SQLModel, table=True):
    """A chemical identifier associated with one or more stationary points.

    Attributes:
        id: Primary key.
        algorithm_id: Foreign key to the generating `IdentityAlgorithmRow`.
        algorithm: Method used to generate the identifier (e.g. ``rdkit inchi``, ``rdkit
            smiles``); its ``kind`` gives the category (e.g. ``stereoisomer``,
            ``formula``).
        value: The resulting identifier string.
        stationary_points: Stationary points sharing this identity.
    """

    __tablename__ = "identity"
    __table_args__ = (
        UniqueConstraint("algorithm_id", "value", name="unique_identity"),
    )

    id: int | None = Field(default=None, primary_key=True)
    algorithm_id: int | None = Field(
        default=None,
        foreign_key="identity_algorithm.id",
        ondelete="CASCADE",
        nullable=False,
        index=True,
    )
    value: str

    algorithm: "IdentityAlgorithmRow" = Relationship(back_populates="identities")
    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="identities", link_model=IdentityStationaryLink
    )
