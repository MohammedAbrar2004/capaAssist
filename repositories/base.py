"""Abstract repository interface — the only contract agents/retrieval code
depend on. `PostgresCapaRepository` implements this now; an
`OracleCapaRepository` implements it later. Swap = new class + `DB_BACKEND`
flag, nothing above this layer changes.

Every method is tenant-scoped (`tenant_id` first positional arg) and
returns/accepts `models.schemas` types — never raw dicts/rows.
"""

from abc import ABC, abstractmethod
from typing import Optional

from models.schemas import (
    ActionTaxonomyEntry,
    AuditTrailEntry,
    Capa,
    CapaAction,
    CapaRCA,
    Category,
    CapaType,
    ContextPackageRecord,
    Employee,
    Evaluation,
    Priority,
    Severity,
    Site,
    Status,
)


class CapaRepository(ABC):
    # --- Core CAPA domain ----------------------------------------------

    @abstractmethod
    def fetch_capa(self, tenant_id: str, capa_id: str) -> Optional[Capa]:
        ...

    @abstractmethod
    def fetch_actions(self, tenant_id: str, capa_id: str) -> list[CapaAction]:
        ...

    @abstractmethod
    def fetch_actions_bulk(
        self, tenant_id: str, capa_ids: list[str]
    ) -> dict[str, list[CapaAction]]:
        """One query for N capa_ids instead of N calls to fetch_actions —
        avoids the N+1 pattern in sql_retrieval.py. See phases/phase2.md
        Sub-Phase 2b."""
        ...

    @abstractmethod
    def fetch_rca(self, tenant_id: str, capa_id: str) -> Optional[CapaRCA]:
        ...

    @abstractmethod
    def fetch_rca_bulk(self, tenant_id: str, capa_ids: list[str]) -> dict[str, CapaRCA]:
        ...

    @abstractmethod
    def fetch_capas_bulk(self, tenant_id: str, capa_ids: list[str]) -> dict[str, Capa]:
        ...

    @abstractmethod
    def fetch_similar_capas(
        self,
        tenant_id: str,
        site_id: Optional[str] = None,
        category_id: Optional[str] = None,
        limit: int = 10,
    ) -> list[Capa]:
        """Structured (SQL) similarity by site/category — distinct from
        the vector store's semantic similarity on root-cause text."""
        ...

    @abstractmethod
    def fetch_effective_actions(self, tenant_id: str) -> list[CapaAction]:
        """Closed actions with a recorded effectiveness signal — the
        candidate pool for the batch vectorization script."""
        ...

    @abstractmethod
    def count_recurrence(self, tenant_id: str, capa_id: str) -> int:
        ...

    @abstractmethod
    def fetch_capas(
        self,
        tenant_id: str,
        limit: int,
        offset: int,
        site_id: Optional[str] = None,
        status_id: Optional[str] = None,
    ) -> list[Capa]:
        """Paginated list for GET /capas. See phases/phase7.md decision 5."""
        ...

    @abstractmethod
    def count_capas(
        self,
        tenant_id: str,
        site_id: Optional[str] = None,
        status_id: Optional[str] = None,
    ) -> int:
        ...

    @abstractmethod
    def fetch_audit_trail(
        self,
        tenant_id: str,
        capa_id: Optional[str] = None,
        agent: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditTrailEntry]:
        """capa_ai_audit_trail has no capa_id column — filters on
        input_payload->>'capa_id' instead. See phases/phase7.md decision 5."""
        ...

    @abstractmethod
    def count_audit_trail(
        self,
        tenant_id: str,
        capa_id: Optional[str] = None,
        agent: Optional[str] = None,
    ) -> int:
        ...

    # --- Master / lookup -------------------------------------------------

    @abstractmethod
    def fetch_severity(self, severity_id: str) -> Optional[Severity]:
        ...

    @abstractmethod
    def fetch_priority(self, priority_id: str) -> Optional[Priority]:
        ...

    @abstractmethod
    def fetch_status(self, status_id: str) -> Optional[Status]:
        ...

    @abstractmethod
    def fetch_capa_type(self, capa_type_id: str) -> Optional[CapaType]:
        ...

    @abstractmethod
    def fetch_category(self, category_id: str) -> Optional[Category]:
        ...

    @abstractmethod
    def fetch_site(self, site_id: str) -> Optional[Site]:
        ...

    @abstractmethod
    def fetch_employees(
        self,
        tenant_id: str,
        site_id: Optional[str] = None,
        group_id: Optional[str] = None,
        role_title: Optional[str] = None,
    ) -> list[Employee]:
        """Direct lookup path for known filters. Distinct from nl2sql.py's
        free-form natural-language path over the same table."""
        ...

    @abstractmethod
    def fetch_action_taxonomy(self, action_type: str) -> list[ActionTaxonomyEntry]:
        """CAPA_AI_ACTION_TAXONOMY rows for one action_type — Generator-only
        steering data. See phases/phase3.md decision 2."""
        ...

    # --- AI-write tables ---------------------------------------------------

    @abstractmethod
    def write_evaluation(self, evaluation: Evaluation) -> None:
        ...

    @abstractmethod
    def write_audit(self, entry: AuditTrailEntry) -> None:
        ...

    @abstractmethod
    def save_context_package(self, record: ContextPackageRecord) -> None:
        ...
