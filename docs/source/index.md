# autostorage

A [SQLModel](https://sqlmodel.tiangolo.com/)/[SQLAlchemy](https://www.sqlalchemy.org/) persistence layer for computational chemistry workflow data, built on top of [`automol`](https://github.com/avcopan/automol). It stores molecular geometries, chemical identities, trajectories, stationary points, calculation results (energies, gradients, Hessians), and the calculations/reaction steps that connect them, as a graph of related rows in a SQLite database.

`GeometryRow` extends `automol.Geometry` directly rather than wrapping it, so geometries already expressed in `automol` types can be persisted with no conversion step (and are validated by automol). Chemical identities (InChI, SMILES, Hill formula) are generated automatically for stationary points using the algorithms in `automol.AlgorithmRegistry`.

:::{toctree}
:maxdepth: 2
:caption: Contents

quickstart
database
:::
