"""Compatibility import for PostgreSQL test configuration."""

from core.database_config import resolve_test_database_url

__all__ = ["resolve_test_database_url"]
