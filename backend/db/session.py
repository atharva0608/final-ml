"""
DB Session shim — re-exports SessionLocal from backend.models.base.

backend.models.base is the single source of truth for the SQLAlchemy engine
and session factory. This shim exists so task modules can import from a
canonical db package path without a circular import chain.
"""
from backend.models.base import SessionLocal  # noqa: F401
