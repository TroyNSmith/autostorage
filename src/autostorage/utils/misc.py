"""Miscellaneous autostorage utilities."""

from typing import Annotated, cast

from pydantic import BaseModel, Field, create_model


def make_fields_optional[ModelT: BaseModel](model_cls: type[ModelT]) -> type[ModelT]:
    """Convert RowModel to an OptionalModel retaining original fields and typing."""
    new_fields = {}

    relationships = getattr(model_cls, "__sqlmodel_relationships__", {})

    for f_name, f_info in model_cls.model_fields.items():
        # Skip relationships
        if f_name in relationships:
            continue

        f_dct = f_info.asdict()

        # Reset default factories to allow for None in OptionalModel
        attrs = dict(f_dct["attributes"])
        attrs.pop("default", None)
        attrs.pop("default_factory", None)

        new_fields[f_name] = (
            Annotated[
                f_dct["annotation"] | None,  # noqa: F821
                *f_dct["metadata"],
                Field(**attrs),
            ],
            None,
        )

    return cast(
        "type[ModelT]",
        create_model(
            f"{model_cls.__name__}Optional",
            __module__=model_cls.__module__,
            __config__=model_cls.model_config,
            **new_fields,
        ),
    )
