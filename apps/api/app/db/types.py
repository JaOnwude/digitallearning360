from enum import StrEnum

from sqlalchemy import Enum


def str_enum(enum_cls: type[StrEnum]) -> Enum:
    """Store enums as checked VARCHARs: easy to extend without ALTER TYPE."""
    return Enum(
        enum_cls,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda e: [m.value for m in e],
    )
