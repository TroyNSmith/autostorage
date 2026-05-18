# Database Connection Manager

The `Database` class serves as the core connection manager for AutoStorage's SQLite database. Built on top of [SQLModel](https://sqlmodel.tiangolo.com/) and [SQLAlchemy](https://www.sqlalchemy.org/), it is responsible for handling connection pooling, session lifecycles, and standard CRUD (Create, Read, Update, Delete) operations with built-in support for relationship eager-loading.

## Initializing the Database
When you initialize the `Database` instance, it automatically connects to the specified SQLite file and builds the schema metadata if it doesn't already exist.

```python
from pathlib import path
from autostorage import Database

# Initialize database
db = Database(path="my_data.db")
```

```{eval-rst}

.. autoclass:: autostorage.database.Database

```

## Adding and Deleting Records
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

```{eval-rst}

.. autofunction:: autostorage.database.Database.add
.. autofunction:: autostorage.database.Database.delete

```

### Auto-Populated Attributes
When adding a new record to the database, attributes like `id` are automatically available after the `add()` method executes, even if it was omitted during initialization:

```python
geo_row = GeometryRow(
    symbols=["O", "H", "H"], 
    coords=[[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, -1.0, 0.0]]
)
print(geo_row.id) # None

db.add(row=geo_row)

print(geo_row.id) # e.g., 1
```

### Find or Add
The `find_or_add()` method is designed to handle idempotent insertions. It should be used primarily when a table enforces a uniqueness constraint (such as hash on the `GeometryRow` object) and a workflow requires a valid database record to establish field relationships (i.e., when a row ID is required for linking). First, `database.find()` is called and if any matches are found, `find_or_add()` will yield all matching rows. If no matches are found, the method will yield from a single `database.add()` instead to ensure iterator behavior is maintained.

```python
geo_row = GeometryRow(
    symbols=["O", "H", "H"], 
    coords=[[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, -1.0, 0.0]]
)

db.add(row=geo_row)

print(geo_row.id) # e.g., 1

for row in db.find_or_add(row=geo_row):
    print(row.id) # e.g., 1
```

```{eval-rst}

.. autofunction:: autostorage.database.Database.find_or_add

```

#### Partial Model Querying
The `PartialMixin` BaseModel has been applied to all database row objects. This method allows the user to define a row for querying without entering all required fields:

```python
# Create a GeometryRow defining only the symbols
partial_geo_row = GeometryRow.partial(symbols=["O", "H", "H"])

for row in db.find(partial_geo_row):
    print(row.coordinates) # Print the coordinates for any row with matching symbols
```



### Eager Loading
By default, SQLModel and SQLAlchemy utilize **Lazy Loading** for related models. Lazy loading defers fetching related data from the database until explicitly requested; when a parent object like `GeometryRow` is queried, the ORM populates the geometry's primary fields but leaves related fields (like *geometryrow.calculations*) empty.

To address the need for related querying, the `Database` wrapper interface exposes an `eager_load` flag across core CRUD methods.

When `eager_load=True` is passed, the `Database` class completely bypasses lazy evaluation. Instead, SQLModel metadata is evaluated at runtime, every declared relationship on the target model is identified, and the query engine is instructed to front load data in related fields.

