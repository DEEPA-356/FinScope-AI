"""
SQLAlchemy declarative base.

All models import from here so Alembic can auto-detect them.
"""

from sqlalchemy.orm import DeclarativeBase, MappedColumn
from sqlalchemy import MetaData

# Naming convention ensures consistent constraint names across migrations
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Shared base class for all SQLAlchemy models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
