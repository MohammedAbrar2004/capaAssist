-- Dedicated read-only Postgres role for NL2SQL (retrieval/nl2sql.py).
-- SELECT-only on the NL2SQL whitelist: CAPA domain + masters + MSTR_TENANT_EMP.
-- Never grant capa_ai_evaluations/capa_ai_audit_trail/capa_ai_context_packages
-- (write-trail tables, not retrieval targets) or INSERT/UPDATE/DELETE on anything.
-- Idempotent — safe to re-run.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'capa_ai_readonly') THEN
        CREATE ROLE capa_ai_readonly LOGIN PASSWORD 'capa_ai_readonly_pw';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE capa_assist TO capa_ai_readonly;
GRANT USAGE ON SCHEMA public TO capa_ai_readonly;

GRANT SELECT ON
    CAPA,
    CAPA_ACTIONS,
    CAPA_RCA,
    CAPA_INVESTIGATIONS,
    CAPA_REVIEWS,
    CAPA_CLOSURE,
    CAPA_CATEGORIES,
    CAPA_SUBCATEGORIES,
    CAPA_TYPE_MASTER,
    CAPA_STATUS_MASTER,
    MSTR_SEVERITY_MASTER,
    MSTR_PRIORITY_MASTER,
    MSTR_STATUS_MASTER,
    MSTR_TENANT_METADATA,
    MSTR_TENANT_SITES,
    MSTR_TENANT_GROUPS,
    MSTR_TENANT_SITE_GROUPS,
    MSTR_TENANT_EMP,
    MSTR_USERS_METADATA
TO capa_ai_readonly;

-- Future tables created in these categories should be granted explicitly
-- here too (no ALTER DEFAULT PRIVILEGES blanket grant — keep the whitelist
-- enumerated and reviewable).
