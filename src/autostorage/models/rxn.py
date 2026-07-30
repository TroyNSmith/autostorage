"""Reaction-related row definitions: stationary points, identities, stages, steps."""

from typing import TYPE_CHECKING, Any

from automol import Identity
from sqlmodel import CheckConstraint, Field, Index, Relationship, UniqueConstraint, text

from .core import BaseRow, _fk_field
from .link import StationaryIdentityLink, StationaryStageLink, StepValidationLink

if TYPE_CHECKING:
    from .calc import CalculationRow, ValidationRow
    from .geom import GeometryRow


# Stationary point rows
class StationaryPointRow(BaseRow, table=True):
    """A stationary point on a potential energy surface.

    Attributes
    ----------
    geometry_id
        Foreign key to the underlying molecular geometry.
    calculation_id
        Foreign key to the calculation that identified this point.
    order
        Hessian index (0 for minima, 1 for first-order saddle points).
    is_pseudo
        Whether this point is not a true stationary point (e.g. constrained).
    is_valid
        Whether `order` agrees with the consensus order of its geometry's
        Hessians (see `autostorage.events.revalidate_geometry_orders_on_insert_update`).
    geometry
        Geometry defining the coordinates of this point.
    calculation
        Calculation that identified this point.
    identities
        Chemical identifiers (e.g. InChI, SMILES) for this point.
    stages
        Reaction stages this stationary point belongs to.
    """

    __tablename__ = "stationary_point"

    geometry_id: int | None = _fk_field("geometry.id")
    calculation_id: int | None = _fk_field("calculation.id")
    order: int = 0
    is_pseudo: bool = False
    is_valid: bool = False

    geometry: "GeometryRow" = Relationship(back_populates="stationary_points")
    calculation: "CalculationRow" = Relationship()
    identities: list["IdentityRow"] = Relationship(
        back_populates="stationary_points", link_model=StationaryIdentityLink
    )
    stages: list["StageRow"] = Relationship(
        back_populates="stationaries", link_model=StationaryStageLink
    )

    def identity(
        self,
        *,
        kind: str | None = None,
        algorithm: Any | None = None,  # noqa: ANN401
    ) -> "IdentityRow | None":
        """Return the first loaded identity matching kind and/or algorithm.

        Searches `self.identities` (the already-loaded relationship list),
        not the database.
        """
        return next(
            (
                i
                for i in self.identities
                if (kind is None or i.kind == kind)
                and (algorithm is None or i.algorithm == algorithm)
            ),
            None,
        )


class IdentityRow(BaseRow, Identity, table=True):
    """A chemical identifier associated with one or more stationary points.

    Attributes
    ----------
    kind
        Category of identifier (e.g. ``stereoisomer``, ``formula``).
    algorithm
        Method used to generate the identifier (e.g. ``rdkit inchi``, ``rdkit smiles``).
    value
        The resulting identifier string.
    stationary_points
        Stationary points sharing this identity.
    identity_extras
        Additional key-value metadata attached to this identity.
    """

    __tablename__ = "identity"
    __table_args__ = (
        UniqueConstraint("kind", "algorithm", "value", name="unique_identity"),
    )

    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="identities", link_model=StationaryIdentityLink
    )
    identity_extras: list["IdentityExtraRow"] = Relationship(back_populates="identity")


class IdentityExtraRow(BaseRow, table=True):
    """Additional key-value metadata attached to a chemical identity.

    Attributes
    ----------
    identity_id
        Foreign key to the parent identity.
    attribute
        Name of the extra attribute.
    value
        Value of the extra attribute.
    identity
        The parent identity this extra belongs to.
    """

    __tablename__ = "identity_extras"

    identity_id: int | None = Field(
        default=None,
        foreign_key="identity.id",
        ondelete="CASCADE",
        nullable=False,
        index=True,
    )

    attribute: str
    value: str

    identity: "IdentityRow" = Relationship(back_populates="identity_extras")


# Reaction rows
class StageRow(BaseRow, table=True):
    """A chemical state (reactant, product, or transition state) in a reaction.

    Attributes
    ----------
    is_ts
        Whether this stage represents a transition state.
    stationaries
        Stationary points that make up this stage.
    steps
        Reaction steps referencing this stage as `stage1`, `stage2`, or
        `stage_ts` (read-only; derived from `StepRow`'s foreign keys).
    """

    __tablename__ = "stage"

    is_ts: bool = False

    stationaries: list["StationaryPointRow"] = Relationship(
        back_populates="stages", link_model=StationaryStageLink
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


class StepRow(BaseRow, table=True):
    """An elementary reaction step connecting a reactant, transition state, and product.

    Attributes
    ----------
    stage_id1, stage_id2
        Foreign keys to the step's two non-TS stages (stored with
        `stage_id1 < stage_id2`).
    stage_id_ts
        Foreign key to the step's transition-state stage, or `None` for a
        barrierless step.
    is_barrierless
        Whether this step proceeds without a formal transition state.
    stage1, stage2
        The step's two non-TS stages.
    stage_ts
        The step's transition-state stage, or `None` if barrierless.
    validations
        Validation calculations performed on this step.
    """

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

    stage_id1: int | None = Field(
        default=None,
        foreign_key="stage.id",
        ondelete="CASCADE",
        nullable=False,
    )
    stage_id2: int | None = Field(
        default=None,
        foreign_key="stage.id",
        ondelete="CASCADE",
        nullable=False,
    )
    stage_id_ts: int | None = Field(
        default=None,
        foreign_key="stage.id",
        ondelete="CASCADE",
    )

    is_barrierless: bool = False

    validations: list["ValidationRow"] = Relationship(
        back_populates="step", link_model=StepValidationLink
    )

    stage1: "StageRow" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[StepRow.stage_id1]"}
    )
    stage2: "StageRow" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[StepRow.stage_id2]"}
    )
    stage_ts: "StageRow" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[StepRow.stage_id_ts]"}
    )
