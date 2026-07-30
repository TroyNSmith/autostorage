"""Reaction-related row definitions: stationary points, identities, stages, steps."""

from typing import TYPE_CHECKING, Any, Self

from automol import Algorithm, Identity
from sqlmodel import (
    CheckConstraint,
    Field,
    Index,
    Relationship,
    UniqueConstraint,
    func,
    select,
    text,
)

from autostorage.exc import MissingPrimaryKeyError
from autostorage.types import CalcType

from .calc import CalculationRow, ModelRow
from .core import BaseRow, _fk_field
from .link import StationaryIdentityLink, StationaryStageLink, StepValidationLink

if TYPE_CHECKING:
    from autostorage.database import Database

    from .calc import ValidationRow
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

    @classmethod
    def query(
        cls,
        db: "Database",
        *,
        ident: Identity,
        model: "ModelRow | None" = None,
        prov: dict[Any, Any] | None = None,
        calc_type: CalcType | None = None,
    ) -> Self | None:
        """Query for stationary point matching geometry, model, and provenance."""
        stmt = (
            select(cls)
            .join(
                StationaryIdentityLink,
                cls.id == StationaryIdentityLink.stationary_id,  # ty:ignore[invalid-argument-type]
            )
            .join(
                IdentityRow,
                IdentityRow.id == StationaryIdentityLink.identity_id,  # ty:ignore[invalid-argument-type]
            )
            .where(
                IdentityRow.kind == ident.kind,
                IdentityRow.algorithm == ident.algorithm,
                IdentityRow.value == ident.value,
            )
        )

        if model or prov or calc_type:
            stmt = stmt.join(
                CalculationRow,
                cls.calculation_id == CalculationRow.id,  # ty:ignore[invalid-argument-type]
            )

        if model:
            if not model.id:
                raise MissingPrimaryKeyError([model])
            stmt = stmt.where(CalculationRow.model_id == model.id)

        if prov:
            stmt = stmt.where(CalculationRow.input_provenance == prov)

        if calc_type:
            stmt = stmt.where(CalculationRow.calc_type == calc_type)

        return db.exec_first(stmt)

    def identity(
        self,
        *,
        kind: str | None = None,
        algorithm: Any | None = None,  # noqa: ANN401
    ) -> "IdentityRow | None":
        """Return the first loaded identity matching kind and/or algorithm.

        Searches `self.identities` (the already-loaded relationship list),
        not the database — use `StationaryPointRow.query` for a DB lookup.
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

    @classmethod
    def find_or_create(
        cls,
        db: "Database",
        *,
        algorithm: Algorithm,
        value: str,
        commit: bool = True,
    ) -> Self:
        """Return the matching identity row, creating and saving one if absent.

        `kind` isn't a parameter here since it's fully determined by
        `algorithm` (see `Identity.from_value`), so matching on
        `(algorithm, value)` is equivalent to `unique_identity`'s full
        `(kind, algorithm, value)` constraint.

        Parameters
        ----------
        commit, optional
            If True (default), commit a newly-created row immediately. If
            False, only flush it (still assigns `.id`), leaving the caller's
            transaction open — for a caller staging several dedup lookups
            that must succeed or fail together.
        """
        stmt = select(cls).where(cls.algorithm == algorithm, cls.value == value)
        existing = db.exec_first(stmt)
        if existing is not None:
            return existing

        row = cls.from_value(value, algorithm=algorithm)
        db.add(row)
        if commit:
            db.commit()
        else:
            db.flush()
        return row


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

    @classmethod
    def query(
        cls,
        db: "Database",
        stationaries: list["StationaryPointRow"],
        *,
        is_ts: bool = False,
    ) -> Self | None:
        """Query for existing stage with stationaries."""
        target_ids = [s.id for s in stationaries]
        if len(target_ids) != len(stationaries):
            raise MissingPrimaryKeyError(list(stationaries))

        stmt = (
            select(cls)
            .join(StationaryStageLink)
            .where(cls.is_ts == is_ts)
            .group_by(cls.id)  # ty:ignore[invalid-argument-type]
            .having(
                func.count(StationaryStageLink.stationary_id) == len(target_ids),  # ty:ignore[invalid-argument-type]
                func.count(
                    func.nullif(
                        StationaryStageLink.stationary_id.in_(target_ids),  # ty:ignore[unresolved-attribute]
                        False,  # noqa: FBT003
                    )
                )
                == len(target_ids),
            )
        )
        return db.exec_first(stmt)

    @classmethod
    def find_or_create(
        cls,
        db: "Database",
        stationaries: list["StationaryPointRow"],
        *,
        is_ts: bool = False,
    ) -> Self:
        """Return the matching stage row, creating and saving one if absent.

        Note
        ----
        Unlike `ModelRow`/`StepRow`, there is no DB-level uniqueness
        constraint backing this dedup, so it relies entirely on
        `StageRow.query`'s app-level lookup.
        """
        existing = cls.query(db, stationaries, is_ts=is_ts)
        if existing is not None:
            return existing

        row = cls(stationaries=stationaries, is_ts=is_ts)
        db.add(row)
        db.commit()
        return row


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
        # constraint. This expression index closes that gap at the DB level,
        # defense-in-depth alongside `StepRow.query`'s app-level lookup.
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

    @classmethod
    def query(
        cls,
        db: "Database",
        stage1: "StageRow",
        stage2: "StageRow",
        stage_ts: "StageRow | None" = None,
    ) -> Self | None:
        """Query for an existing step connecting specific stages."""
        if not stage1.id or not stage2.id or (stage_ts and not stage_ts.id):
            raise MissingPrimaryKeyError(
                [s for s in [stage1, stage2, stage_ts] if s is not None]
            )

        # Enforce the database CheckConstraint: stage_id1 < stage_id2
        id1, id2 = sorted([stage1.id, stage2.id])
        ts_id = stage_ts.id if stage_ts else None

        stmt = select(cls).where(
            cls.stage_id1 == id1,
            cls.stage_id2 == id2,
            cls.stage_id_ts == ts_id,
        )
        return db.exec_first(stmt)

    @classmethod
    def find_or_create(
        cls,
        db: "Database",
        stage1: "StageRow",
        stage2: "StageRow",
        stage_ts: "StageRow | None" = None,
    ) -> Self:
        """Return the matching step row, creating and saving one if absent."""
        existing = cls.query(db, stage1, stage2, stage_ts)
        if existing is not None:
            return existing

        row = cls(stage1=stage1, stage2=stage2, stage_ts=stage_ts)
        db.add(row)
        db.commit()
        return row
