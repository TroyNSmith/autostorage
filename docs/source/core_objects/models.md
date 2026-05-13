# Core Models

## Calculation

The `Calculation` model is the core object for defining run parameters.

**Table 1.1: Calculation model.**
| Field              | Type   | Description                                      |
| ------------------ | ------ | ------------------------------------------------ |
| `program`          | `str`  | Quantum chemistry program used (psi4, ORCA, ...) |
| `program_keywords` | `dict` | Quantum chemistry program keywords.              |
| `super_program`    | `str`  | Geometry optimizer program (geomeTRIC, ...)      |
| `super_keywords`   | `dict` | Geometry optimizer keywords.                     |
| `cmdline_args`     | `list` | Command line arguments.                          |
| `calc_type`        | `str`  | Calculation type (energy, optimization, ...)     |
| `method`           | `str`  | Computational method (B3LYP, MP2, ...)           |
| `basis`            | `str`  | Basis set.                                       |


A minimal working example is shown below:

```python
from autostorage import Calculation

calc = Calculation(program="ORCA", method="B3LYP")

...
```

### CalculationRow

`Calculation` is constructed via Pydantic BaseModel and is intended for use as a general template for defining user inputs to QC calculations. The `CalculationRow` inherits the `Calculation` BaseModel and re-defines field typings to ensure SQL compatibility. Due to inheritance, the `Calculation` and `CalculationRow` models can be used interchangeably.

```python
from autostorage import CalculationRow

calc = CalculationRow(program="ORCA", method="B3LYP")

...
```

### ProvenanceRow

Values collected during run time including *program version*, *wall time*, ..., are stored in the `ProvenanceRow` object.

**Table 1.2: ProvenanceRow model.**
| Field              | Type   | Description                                      |
| ------------------ | ------ | ------------------------------------------------ |
| `program`          | `str`  | Quantum chemistry program used (psi4, ORCA, ...) |
| `program_keywords` | `dict` | Quantum chemistry program keywords.              |
| `super_program`    | `str`  | Geometry optimizer program (geomeTRIC, ...)      |
| `super_keywords`   | `dict` | Geometry optimizer keywords.                     |
| `cmdline_args`     | `list` | Command line arguments.                          |
| `calc_type`        | `str`  | Calculation type (energy, optimization, ...)     |
| `method`           | `str`  | Computational method (B3LYP, MP2, ...)           |
| `basis`            | `str`  | Basis set.                                       |