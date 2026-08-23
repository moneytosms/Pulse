"""Declarative base for all ORM models.

Phase 1 modules subclass `Base` in their own `models.py`. Nothing is
registered against it yet — Phase 0 only needs the base to exist so
`env.py` has metadata to target.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
