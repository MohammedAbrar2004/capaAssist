"""Shared fixtures for integration tests.

These hit the live seeded `capa_assist` dev DB (see phases/phase1.md). They
assume `python seeds/load_seed.py` has been run for TENANT_ACERTECH. If the DB
is unreachable, the whole integration suite is skipped (not failed) — these
are environment-dependent, not unit tests.
"""

import sys
from pathlib import Path

import pytest

# Safety net: make the service root importable even if pytest's rootdir
# discovery differs (config/services/repositories are top-level modules).
SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

import config  # noqa: E402


@pytest.fixture(scope="session")
def tenant() -> str:
    return config.CAPA_TENANT_ID or "TENANT_ACERTECH"


@pytest.fixture(scope="session")
def repo():
    """The repository under test, via the same factory runtime code uses."""
    try:
        from services.db import get_repository

        r = get_repository()
        # Cheap connectivity probe — skip the suite if the dev DB is down.
        r.fetch_severity("SEV_HIGH")
        return r
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"capa_assist dev DB unreachable: {exc}")


@pytest.fixture()
def db_conn():
    """Raw psycopg2 connection for asserting AI-table writes round-trip.

    The repository deliberately exposes no readers for the capa_ai_* tables
    (they're written at runtime, read by analytics/ops, not by agents), so
    tests read them back directly. Test-only — runtime code never does this.
    """
    import psycopg2

    conn = psycopg2.connect(config.DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()
