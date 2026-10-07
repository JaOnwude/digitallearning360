"""Row-level security helpers for migrations (spec R1).

Every tenant table gets RLS enabled *and forced* (so even the table owner is subject to it)
with one policy: rows are visible/writable only when school_id matches the transaction's
`app.school_id` setting. If the setting is missing, nothing matches.
"""

from alembic import op

APP_ROLE = "dl360_app"


def enable_tenant_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON {table}
        USING (school_id = NULLIF(current_setting('app.school_id', true), '')::uuid)
        WITH CHECK (school_id = NULLIF(current_setting('app.school_id', true), '')::uuid)
        """
    )


def disable_tenant_rls(table: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


def if_app_role(sql: str) -> None:
    """Run a GRANT/REVOKE only where the restricted app role exists (local, tests).

    On managed hosts the app uses the owner role, which FORCE RLS still constrains.
    """
    op.execute(
        f"""
        DO $$ BEGIN
          IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            {sql};
          END IF;
        END $$;
        """
    )
