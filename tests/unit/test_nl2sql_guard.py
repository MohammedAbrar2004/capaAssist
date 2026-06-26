"""Pure unit tests for retrieval/nl2sql.py's _guard() — no network, no DB.
Asserts the SQL-injection/scope guard rejects every attack pattern and
accepts well-formed whitelisted queries, per phases/phase2.md decision 2.
"""

import sys
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from retrieval.nl2sql import GuardRejection, _guard  # noqa: E402


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM mstr_users_metadata WHERE tenant_id = %(tenant_id)s; DROP TABLE capa;",
        "SELECT * FROM capa WHERE tenant_id = %(tenant_id)s UNION SELECT * FROM mstr_users_metadata",
        "WITH x AS (SELECT * FROM capa) SELECT * FROM x WHERE tenant_id = %(tenant_id)s",
        "SELECT * FROM capa_ai_audit_trail WHERE tenant_id = %(tenant_id)s",
        "SELECT * FROM capa",  # no tenant filter at all
        "DELETE FROM capa WHERE tenant_id = %(tenant_id)s",
        "DROP TABLE capa",
        "SELECT * FROM capa WHERE tenant_id = 'TENANT_ACERTECH'",  # literal, not the bound placeholder
        "INSERT INTO capa (capa_id) VALUES ('x')",
        "SELECT pg_sleep(100)",
    ],
)
def test_guard_rejects_attacks(sql):
    with pytest.raises(GuardRejection):
        _guard(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT emp_id, full_name, role_title FROM mstr_tenant_emp WHERE tenant_id = %(tenant_id)s",
        "SELECT c.capa_id, a.action_title FROM capa c JOIN capa_actions a ON a.capa_id = c.capa_id "
        "WHERE c.tenant_id = %(tenant_id)s LIMIT 10",
        "select * from capa where tenant_id = %(tenant_id)s",  # lowercase still passes
    ],
)
def test_guard_accepts_whitelisted_queries(sql):
    result = _guard(sql)
    assert "limit" in result.lower()


def test_guard_appends_limit_when_missing():
    result = _guard("SELECT * FROM capa WHERE tenant_id = %(tenant_id)s")
    assert "LIMIT 50" in result


def test_guard_preserves_explicit_limit():
    result = _guard("SELECT * FROM capa WHERE tenant_id = %(tenant_id)s LIMIT 5")
    assert result.count("LIMIT") == 1
    assert "LIMIT 5" in result


def test_guard_escapes_literal_percent_without_breaking_placeholder():
    result = _guard(
        "SELECT * FROM mstr_tenant_emp WHERE tenant_id = %(tenant_id)s "
        "AND role_title ILIKE '%EHS Officer%'"
    )
    assert "%(tenant_id)s" in result
    assert "%%EHS Officer%%" in result
