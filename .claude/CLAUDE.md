# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

autostorage is a SQLModel/SQLAlchemy persistence layer for computational chemistry workflow
data, built on top of `automol`. It stores molecular geometries, identities, trajectories,
stationary points, calculation results, and the calculations/steps that connect them, as a
graph of related database rows.

## Commands

All tasks run through Pixi (`pixi run <task>`), defined in `pixi.toml` under `[feature.dev.tasks]`:

- `pixi run fmt` — format with Ruff
- `pixi run lint` — lint with Ruff (`--fix`)
- `pixi run types` — static type-check with `ty`
- `pixi run imports` — enforce module layering with `lint-imports` (import-linter)
- `pixi run test` — run the full pytest suite
- `pixi run pre-commit` — run all of the above via lefthook, in order (fmt → lint → types → imports → test), then check the tree is clean
- `pixi run cov-view` — open the HTML coverage report
- `pixi run local` — toggle `pixi.toml`'s `automol` dependency between the pinned release and a
  local `../automol` checkout, via the `# local:true`/`# local:false` comment markers already in
  the file (see "Relationship to automol" below)
- `pixi run local-pre-commit` — a second lefthook target, distinct from `pre-commit`
- `pixi run docs-build` / `pixi run docs-view` — build/view the Sphinx docs (`feature.docs` env)

Single test: invoke `pytest` directly inside the pixi env, e.g.
`pixi run -e dev pytest tests/test_models.py::TestGeometryRow::test_name` (tests are organized
into `Test*` classes grouped by row/function under test).

Note: pytest is configured with `--doctest-modules`, so doctests in `src/` docstrings are
collected and run as part of the suite. Coverage must stay ≥80% (`fail_under = 80` in
`pyproject.toml`), with branch coverage enabled.

Don't invoke bare `python`/`python3` — `automol` and other deps aren't on the system interpreter,
only inside the pixi env. Always go through `pixi run` (e.g. `pixi run -e dev pytest ...`).

## Architecture

### Module layering (enforced by import-linter)

`pyproject.toml` defines a strict layer contract ("Autostorage Layering") — higher layers may
depend on lower ones, never the reverse:

```
autostorage.database            (highest)
autostorage.events
autostorage.query | autostorage.property
autostorage.models
autostorage.types                (lowest)
```

Adding an import that violates this order will fail `pixi run imports`. `autostorage` is a flat
module structure — all modules live directly in `src/autostorage/`.

### Relationship to automol

`GeometryRow` extends `automol.Geometry` directly rather than wrapping it, so automol's
validation (element symbols, spin parity, atom count, `pint` coordinates) applies to it. Identity
algorithms come from `automol.AlgorithmRegistry` (module-level `Algorithm` instances such as
`automol.rdkit_inchi`) and are mirrored by name into `IdentityAlgorithmRow`. Any conversion
to/from other external formats is delegated to automol rather than reimplemented here.

### Current module map

- `models.py` — SQLModel row definitions, organized in sections:
  - Link tables (named alphabetically by the entities they connect): `CalculationGeometryLink`,
    `CalculationTrajectoryLink`, `GeometryTrajectoryLink`, `IdentityStationaryLink`,
    `StageStationaryLink`, `StepValidationLink`
  - Existential data rows: `GeometryRow` (extends `automol.Geometry`), `TrajectoryRow`,
    `ModelRow`, `CalculationRow`, `PropertyKindRow` (keyed by name), `PropertyValueRow`,
    `ValidationRow`
  - Stationary point rows: `StationaryPointRow`
  - Reaction network rows: `StageRow`, `StepRow` (a step between two stages, with a barrierless
    flag)
  - Identity rows: `IdentityAlgorithmRow` (mirrors an `automol.Algorithm`), `IdentityRow`

- `property.py` — `PropertyKind` specs (name, validation function, storage dtype) and the
  `PropertyKindRegistry`, with the default `energy`, `gradient`, and `hessian` kinds.

- `query.py` — Select-statement factories (e.g. `stationary_point_by_identity`).

- `events.py` — `AutostorageSession` (the session type the listeners below are bound to) and
  SQLAlchemy ORM event listeners, by concern:
  - Registry seeding: `create_identity_algorithms`, `create_property_kinds`
  - Property validation: `verify_property_values_before_flush` (shape check + dtype cast),
    `verify_valid_stationary_has_hessian`
  - Trajectory validation: `verify_trajectory_geometry_ndim` (ensures geometry index length
    matches trajectory ndim, inferring and persisting it if unset)
  - Auto-managed identities: `add_registry_identities_before_flush` attaches an `IdentityRow` for
    every registered algorithm to new stationary points (and regenerates them when the geometry
    is reassigned). Failing algorithms are skipped with an `IdentityGenerationWarning`.
  - Step validation: `sort_step_stage_ids` (auto-sorts stage_id1 < stage_id2),
    `verify_step_barrierless_consistency` (verifies is_barrierless matches stage_id_ts state)

- `database.py` — `Database`: SQLite engine/session manager (also a context manager). `__init__`
  creates the engine (with `PRAGMA foreign_keys=ON` and a sort-keys JSON serializer), the schema
  via `SQLModel.metadata.create_all`, and seeds the registry tables; `session()` returns a fresh
  `AutostorageSession` (use as a context manager; nothing auto-commits); `close()` disposes the
  engine.

- `types.py` — Type definitions and utilities:
  - `Role` (StrEnum: INPUT/OUTPUT) — relationship between calculations and geometries/trajectories
  - `CompressedArrayTypeDecorator` / `CompressedJSONTypeDecorator` — SQLAlchemy `TypeDecorator`s
    storing NumPy arrays / JSON as zlib-compressed binary data (decompression is size-capped)
  - `_fk_field()` — helper for building foreign-key fields with ON DELETE CASCADE

### Docstrings

Google docstring convention (`tool.ruff.lint.pydocstyle` = `"google"`, matching automol), and
doctest examples in docstrings are executed as tests — keep them runnable and accurate.

### Notes

- Minimize chat/response verbosity when performing work to reduce unnecessary token costs.
- Keep docstrings and comments minimal: one-line Google-style summaries where the convention
  allows, no restating what a name/type hint already conveys. Reserve comments for genuinely
  non-obvious invariants — most docstrings in this repo don't need that much.