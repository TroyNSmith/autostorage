"""AutoStorage demo script."""

# %%
import sys
from pathlib import Path

import autogeom
import py3Dmol
from IPython import get_ipython
from IPython.display import display

from autostorage import (
    AutostorageSession,
    CalculationGeometryLink,
    CalculationTrajectoryLink,
    Database,
    GeometryRow,
    GeometryTrajectoryLink,
    PropertyValueRow,
    Role,
    StationaryPointRow,
    TrajectoryRow,
    query,
    rdkit_inchi,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common
import orca

common.OUT_DIR.mkdir(parents=True, exist_ok=True)
db = Database(common.DB_PATH)

HARTREE_TO_KCAL = 627.509474


def show(*objs: object) -> None:
    """Display objects in Jupyter; skipped when run as a plain script."""
    if get_ipython() is None:
        return
    for obj in objs:
        # Displaying a py3Dmol view directly would also print its text repr
        if isinstance(obj, py3Dmol.view):
            obj.show()
        else:
            display(obj)


# %% [markdown]
# ## Step 1: Conformer search for trans-pent-2-ene


# %%
def step1_goat(sess: AutostorageSession) -> None:
    """Run a GOAT conformer search and refine the conformer energies."""
    work_dir = common.OUT_DIR / "1_GOAT"

    stmt = query.stationary_point_by_identity(rdkit_inchi, common.PENT2ENE_INCHI)
    if sess.exec(stmt).first() is not None:
        msg = "Pent-2-ene conformers already exist."
        print(msg)
        return

    xtb = common.get_or_create_model(sess, "xtb")
    hf3c = common.get_or_create_model(sess, "hf-3c")

    guess = common.from_smiles(common.PENT2ENE_SMILES)
    goat = orca.run(guess, xtb, "goat", work_dir / "goat")
    # The conformer ensemble is an unordered trajectory (no index on its geometries)
    ensemble = TrajectoryRow()
    goat.calculation.trajectory_links.append(
        CalculationTrajectoryLink(trajectory=ensemble, role=Role.OUTPUT)
    )
    sess.add(goat.calculation)
    for i, (conf, _) in enumerate(goat.frames("goat.finalensemble.xyz")):
        ensemble.geometry_links.append(GeometryTrajectoryLink(geometry=conf))
        sess.add(StationaryPointRow(calculation=goat.calculation, geometry=conf))

        ene = orca.run(conf, hf3c, "energy", work_dir / f"energy_{i}")
        sess.add(
            PropertyValueRow(
                property_kind_name="energy",
                calculation=ene.calculation,
                geometry=conf,
                value=ene.energy(),
            )
        )

    sess.commit()


with db.session() as sess:
    step1_goat(sess)

# %%
# Diplaying the GOAT conformers with their relative HF-3c energies
with db.session() as sess:
    hf3c = common.get_or_create_model(sess, "hf-3c")
    stmt = query.stationary_point_by_identity(rdkit_inchi, common.PENT2ENE_INCHI)
    conformers = [stp for stp in sess.exec(stmt) if stp.calculation.calc_type == "goat"]
    energies = [common.energy(stp.geometry, hf3c) for stp in conformers]
    for stp, ene in sorted(zip(conformers, energies, strict=True), key=lambda x: x[1]):
        rel = (ene - min(energies)) * HARTREE_TO_KCAL
        print(f"Conformer {stp.id}: {rel:.2f} kcal/mol")
        show(autogeom.render_svg(stp.geometry))

# %% [markdown]
# ## Step 2: Optimize the lowest-energy conformer and the hydroxyl radical


# %%
def step2_opt(sess: AutostorageSession) -> None:
    """Optimize the lowest-energy conformer and the hydroxyl radical."""
    work_dir = common.OUT_DIR / "2_OPT"

    stmt = query.stationary_point_by_identity(rdkit_inchi, common.PENT2ENE_INCHI)
    pent2ene = sess.exec(stmt).all()
    if any(stp.calculation.calc_type == "opt" for stp in pent2ene):
        msg = "Optimized pent-2-ene is already stored."
        print(msg)
        return

    hf3c = common.get_or_create_model(sess, "hf-3c")
    conformers = [stp for stp in pent2ene if stp.calculation.calc_type == "goat"]
    lowest = min(conformers, key=lambda stp: common.energy(stp.geometry, hf3c))

    common.optimize(sess, lowest.geometry, hf3c, work_dir / "pent2ene")
    hydroxyl = common.from_smiles(common.HYDROXYL_SMILES)
    common.optimize(sess, hydroxyl, hf3c, work_dir / "hydroxyl")
    sess.commit()


with db.session() as sess:
    step2_opt(sess)


# %%
def optimized(sess: AutostorageSession, inchi: str) -> GeometryRow:
    """Get the geometry of an optimized minimum by InChI."""
    stmt = query.stationary_point_by_identity(rdkit_inchi, inchi)
    return next(
        stp.geometry for stp in sess.exec(stmt) if stp.calculation.calc_type == "opt"
    )


# The optimized reactants, labeled by atom index
with db.session() as sess:
    show(
        autogeom.view(optimized(sess, common.PENT2ENE_INCHI), label=True),
        autogeom.view(optimized(sess, common.HYDROXYL_INCHI), label=True),
    )


# %% [markdown]
# ## Step 3: Formation of the abstraction complex
def step_3(sess: AutostorageSession) -> None:
    """Form the abstraction complex between pent-2-ene and the hydroxyl radical."""
    work_dir = common.OUT_DIR / "3_COMPLEX"

    pent2ene_geo = optimized(sess, common.PENT2ENE_INCHI)
    hydroxyl_geo = optimized(sess, common.HYDROXYL_INCHI)

    xtb = common.get_or_create_model(sess, "xtb")
    hf3c = common.get_or_create_model(sess, "hf-3c")
    # `place` only moves the hydroxyl, so join it to pent-2-ene. The new row avoids
    # reusing the hydroxyl row's id, which `place` copies.
    hydroxyl_geo = autogeom.place(hydroxyl_geo, pent2ene_geo, (0, 10), 1.4)
    complex_geo = GeometryRow(
        **autogeom.join([pent2ene_geo, hydroxyl_geo]).model_dump()
    )

    const = orca.run(
        complex_geo,
        xtb,
        "opt",
        work_dir / "constrained",
        "%geom constraints {C 3 C} {C 10 C} {C 15 C} end end",
    )
    start = const.geometry()
    const.calculation.geometry_links.append(
        CalculationGeometryLink(geometry=start, role=Role.OUTPUT)
    )
    sess.add(const.calculation)

    opt = orca.run(start, hf3c, "opt", work_dir / "optimized")

    show(autogeom.view(opt.geometry))


with db.session() as sess:
    step_3(sess)


# %%
