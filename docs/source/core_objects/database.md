# The Database

The `Database` class serves as the core connection manager for AutoStorage's SQLite database. Built on top of [SQLModel](https://sqlmodel.tiangolo.com/) and [SQLAlchemy](https://www.sqlalchemy.org/), it is responsible for handling connection pooling, session lifecycles, and standard CRUD (Create, Read, Update, Delete) operations with built-in support for relationship eager-loading.

## Quick Start & Usage

### Initializing the Database
When you initialize the `Database` instance, it automatically connects to the specified SQLite file and builds the schema metadata if it doesn't already exist.

```python
from pathlib import path
from autostorage import Database

# Initialize database
db = Database(path="my_data.db")
```

### Adding and Deleting Records
The interface provides convenient wrappers around typical SQLAlchemy boilerplate:

```python
from autostorage import GeometryRow

geo_row = GeometryRow(
    symbols=["O", "H", "H"], 
    coords=[[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, -1.0, 0.0]]
)

db.add(row=geo_row)

db.delete(row=geo_row)
```

When adding a new record to the database, attributes like `id` are automatically populated after the `add()` method executed, even if it was omitted during initialization:

```python
from autostorage import GeometryRow

geo_row = GeometryRow(
    symbols=["O", "H", "H"], 
    coords=[[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, -1.0, 0.0]]
)
print(geo_row.id) # None

db.add(row=geo_row)

print(geo_row.id) # e.g., 1
```

## API Reference

```{eval-rst}

.. py:currentmodule:: autostorage.database

.. automodule:: autostorage.database
    :members:

```