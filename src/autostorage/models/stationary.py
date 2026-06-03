"""Stationary point models."""

from typing import TYPE_CHECKING

from automol import Identity
from pydantic import ConfigDict
from sqlmodel import Field, Relationship

from ..types import RowID
from .base import BaseRow
from .links import StationaryIdentityLink, StationaryStageLink

if TYPE_CHECKING:
    from .calculation import CalculationRow
    from .geometry import GeometryRow
    from .reaction import StageRow


class StationaryPointRow(BaseRow, table=True):
    """
    Definition of a stationary point on a potential energy surface.

    Attributes
    ----------
    geometry_id
        Foreign key to the underlying molecular geometry.
    calculation_id
        Foreign key to the calculation identifying this point.
    order
        Hessian index (0 for minima, 1 for saddle points).
    is_pseudo
        Flag for points that are not true stationary points (e.g., constrained).
    [SQL] geometry
        GeometryRow defining the point's coordinates.
    [SQL] calculation
        Parent CalculationRow.
    [SQL] identities
        List of chemical identifiers (InChI, etc.).
    [SQL] metrics
        Comparison metrics (conformer analysis).
    [SQL] stages
        Reaction stages this stationary point belongs to.
    """

    # - SQL Metadata ------------------
    __tablename__ = "stationary_point"
    model_config = ConfigDict(arbitrary_types_allowed=True)
    # - Row id ------------------------
    id: RowID | None = Field(default=None, primary_key=True)
    # - Foreign keys ------------------
    geometry_id: RowID = Field(foreign_key="geometry.id", ondelete="CASCADE")
    calculation_id: RowID = Field(foreign_key="calculation.id", ondelete="CASCADE")
    # - Attributes --------------------
    order: int = 0
    is_pseudo: bool = False
    # - SQLModel relationships --------
    geometry: "GeometryRow" = Relationship(back_populates="stationary_points")
    calculation: "CalculationRow" = Relationship(back_populates="stationary_points")

    identities: list["IdentityRow"] = Relationship(
        back_populates="stationary_points", link_model=StationaryIdentityLink
    )
    metrics: list["MetricRow"] = Relationship(
        back_populates="stationary_point",
    )
    stages: list["StageRow"] = Relationship(
        back_populates="stationary_points", link_model=StationaryStageLink
    )


class IdentityRow(BaseRow, Identity, table=True):
    """
    Chemical identifiers for stationary points.

    Attributes
    ----------
    kind
        Category of identity (e.g., 'stereoisomer', 'formula').
    algorithm
        The method used (e.g., 'InChI', 'SMILES').
    value
        The resulting string identifier.
    [SQL] stationary_points
        Stationary points sharing this identity.
    """

    # - SQL Metadata ------------------
    __tablename__ = "identity"
    # - Row id ------------------------
    id: RowID | None = Field(default=None, primary_key=True)
    # - Foreign keys ------------------
    # - Attributes --------------------
    # - SQLModel relationships --------
    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="identities", link_model=StationaryIdentityLink
    )

    @staticmethod
    def from_identity(ident: Identity) -> "IdentityRow":
        """
        Instantiate IdentityRow from Identity.

        Returns
        -------
        IdentityRow
        """
        return IdentityRow(**ident.model_dump())


class IdentityExtraRow(BaseRow, table=True):
    """
    Extra values to attach to stationary point identity entry.

    Attributes
    ----------
    identity_id
        Foreign key to the parent identity.
    attribute
        Label of extra.
    value
        Value of extra.
    """

    # - SQL Metadata ------------------
    __tablename__ = "identity_extras"
    # - Row id ------------------------
    id: RowID | None = Field(default=None, primary_key=True)
    # - Foreign keys ------------------
    identity_id: int = Field(foreign_key="identity.id", ondelete="CASCADE")
    # - Attributes --------------------
    attribute: str
    value: str
    # - SQLModel relationships --------


class MetricRow(BaseRow, table=True):
    """
    Metrics used for comparing and filtering conformers or stationary points.

    Attributes
    ----------
    stationary_id
        Foreign key to the associated stationary point.
    type
        Type of metric (e.g., 'Inertia Tensor').
    algorithm
        Algorithm used (e.g., 'Kabsch').
    value
        The calculated metric value.
    [SQL] stationary_point
        The parent StationaryPointRow.
    """

    # - SQL Metadata ------------------
    __tablename__ = "metric"
    # - Row id ------------------------
    id: RowID | None = Field(default=None, primary_key=True)
    # - Foreign keys ------------------
    stationary_id: RowID = Field(
        foreign_key="stationary_point.id",
        index=True,
        description="Foreign key to the linked stationary point.",
    )
    # - Attributes --------------------
    type: str = Field(description="Category of the metric (Inertia Tensor, ...)")
    algorithm: str = Field(description="Method used to determine metric (Kabsch, ...)")
    value: str = Field(description="Value of the metric algorithm.")
    # - SQLModel relationships --------
    stationary_point: "StationaryPointRow" = Relationship(back_populates="metrics")
