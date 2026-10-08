"""Imports every feature's models so Base.metadata knows all tables (Alembic, tests).

When a feature adds a models.py, import it here.
"""

import app.academics.models
import app.audit.models
import app.auth.models
import app.fees.models
import app.results.models
import app.students.models
import app.tenancy.models  # noqa: F401
from app.db.base import Base


def tenant_table_names() -> list[str]:
    """Every table with a school_id column. Each one must have an RLS policy (R1, AC1)."""
    return sorted(t.name for t in Base.metadata.sorted_tables if "school_id" in t.columns)
