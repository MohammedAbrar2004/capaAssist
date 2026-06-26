"""Pydantic contracts for everything crossing a repository/agent boundary.

Mapped 1:1 onto the Postgres mirror (`seeds/schema.sql`), real Oracle
column names preserved as field names. Controlled-vocab fields (severity,
priority, status, capa_type names) are typed `str` for now — they get
tightened to `Literal[...]` once the master vocab is minted during seed
extraction (Phase 1b). No raw dicts cross a repository or agent boundary.
"""

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class OrmBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Tier 2 — master / org context -----------------------------------------

class Tenant(OrmBase):
    tenant_id: str
    tenant_name: str
    domain: str
    status_id: str
    contact_name: str
    contact_email: str


class Site(OrmBase):
    site_id: str
    tenant_id: str
    site_name: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    site_manager: Optional[str] = None
    status_id: str
    meta: Optional[str] = None


class Group(OrmBase):
    group_id: str
    tenant_id: str
    group_name: str
    group_description: str
    group_manager_email: Optional[str] = None
    status_id: str


class User(OrmBase):
    user_email: str
    tenant_id: str
    full_name: str
    status_id: str
    group_id: Optional[str] = None


class Employee(OrmBase):
    """MSTR_TENANT_EMP — employee/org-directory record (role + role_description),
    distinct from User's login-identity fields. See phases/phase2.md decision 1."""

    emp_id: str
    tenant_id: str
    site_id: str
    group_id: str
    user_email: Optional[str] = None
    full_name: str
    role_title: Optional[str] = None
    role_description: Optional[str] = None
    status_id: str
    created_date: Optional[datetime] = None


class Severity(OrmBase):
    severity_id: str
    severity_name: str
    severity_level: int
    description: Optional[str] = None


class Priority(OrmBase):
    priority_id: str
    priority_level: str
    description: Optional[str] = None


class Status(OrmBase):
    status_id: str
    status: str
    status_description: str
    source_table: str


class CapaType(OrmBase):
    capa_type_id: str
    capa_type_name: str
    capa_type_description: Optional[str] = None


class Category(OrmBase):
    category_id: str
    tenant_id: str
    parent_category_id: Optional[str] = None
    category_name: str
    category_description: Optional[str] = None


class Subcategory(OrmBase):
    subcategory_id: str
    category_id: str
    tenant_id: str
    subcategory_name: str
    subcategory_description: Optional[str] = None


# --- Tier 1 — core CAPA domain ----------------------------------------------

class Capa(OrmBase):
    capa_id: str
    tenant_id: str
    site_id: str
    source_module: str
    source_record_id: str
    owner_group_id: str
    capa_title: str
    capa_description: str
    rca_method_id: Optional[str] = None
    root_cause: Optional[str] = None
    priority_id: str
    severity_id: str
    capa_type_id: str
    status_id: str
    created_by: str
    assigned_to: Optional[str] = None
    created_date: Optional[datetime] = None
    due_date: date
    completed_date: Optional[date] = None
    capa_closure_date: Optional[date] = None
    closure_comments: Optional[str] = None
    recurrence_count: int = 0
    linked_capa_ids: Optional[str] = None
    risk_level: Optional[str] = None
    estimated_cost: Optional[float] = None
    actual_cost: Optional[float] = None
    business_impact: Optional[str] = None
    external_reference: Optional[str] = None
    regulatory_requirement: Optional[str] = None
    is_recurring: int = 0
    last_updated_at: Optional[datetime] = None
    last_updated_by: Optional[str] = None


class CapaAction(OrmBase):
    action_id: str
    capa_id: str
    tenant_id: str
    site_id: str
    action_title: str
    action_description: str
    priority_id: str
    capa_type_id: str
    severity_id: str
    created_date: Optional[datetime] = None
    created_by: Optional[str] = None
    assigned_to: str
    status_id: str
    due_date: date
    updated_by: Optional[str] = None
    updated_date: Optional[datetime] = None
    completion_comments: Optional[str] = None
    completion_date: Optional[date] = None
    estimated_hours: Optional[float] = None
    actual_hours: Optional[float] = None
    blocked_by: Optional[str] = None
    dependency_type: Optional[str] = None
    verification_required: int = 0
    verified_by: Optional[str] = None
    verified_date: Optional[datetime] = None
    evidence_required: Optional[list[str]] = None


class CapaActionPlan(OrmBase):
    action_plan_id: str
    capa_id: str
    tenant_id: str
    site_id: str
    action_id: str
    action_plan_description: str
    planned_start_date: date
    planned_end_date: date
    actual_start_date: Optional[date] = None
    actual_end_date: Optional[date] = None
    owned_by: str
    status_id: Optional[str] = None


class CapaInvestigation(OrmBase):
    investigation_id: str
    capa_id: str
    tenant_id: str
    site_id: str
    investigation_title: str
    investigation_description: str
    investigation_date: Optional[datetime] = None
    investigator_email: str
    investigation_outcome: str


class CapaReview(OrmBase):
    review_id: str
    capa_id: str
    tenant_id: str
    site_id: str
    reviewed_by: str
    review_outcome: str
    review_iteration: Optional[int] = None
    reviewer_comments: str
    review_date: Optional[datetime] = None
    review_type: Optional[str] = None
    next_review_date: Optional[date] = None
    recurring_review: Optional[int] = None
    review_status_id: Optional[str] = None


class CapaClosure(OrmBase):
    closure_id: str
    capa_id: str
    tenant_id: str
    site_id: str
    closed_by: str
    closure_date: Optional[datetime] = None
    closure_status: Optional[str] = None
    approval_status: Optional[str] = None
    approved_by: Optional[str] = None
    closure_comments: Optional[str] = None


class CapaApproval(OrmBase):
    approval_id: str
    capa_id: str
    tenant_id: str
    site_id: str
    approver_email: str
    approval_status: str
    approval_date: Optional[datetime] = None
    comments: Optional[str] = None


# --- Tier 4 — AI-service-specific -------------------------------------------

class CapaRCA(OrmBase):
    """Isolated AI-side extension — see phase1.md "RCA table"; deletable
    as a single table if the real Oracle system grows native support."""

    rca_id: str
    capa_id: str
    tenant_id: str
    contributing_factors: list[str] = []
    failed_controls: list[str] = []
    missing_controls: list[str] = []
    root_cause_category: Optional[str] = None


class Evaluation(OrmBase):
    eval_id: str
    action_id: str
    tenant_id: str
    score: float
    weakness_level: str
    dimension_results: dict
    model_version: Optional[str] = None
    created_at: Optional[datetime] = None


class AuditTrailEntry(OrmBase):
    request_id: str
    tenant_id: str
    agent: str
    input_payload: dict
    output_payload: dict
    user_decision: Optional[str] = None
    model_version: Optional[str] = None
    created_at: Optional[datetime] = None


class ContextPackageRecord(OrmBase):
    context_id: str
    request_id: str
    tenant_id: str
    capa_id: Optional[str] = None
    package_payload: dict
    created_at: Optional[datetime] = None


# =============================================================================
# Agent-facing contracts (Phase 2+). Confirmed against the minted master
# vocab in seeds/data/*.json — these literal sets match the 5 seeded
# severities/priorities, 4 capa_types, and 7 source_modules exactly.
# =============================================================================

SourceModule = Literal[
    "Incident", "Audit", "Risk", "NCR", "Inspection", "Near Miss", "Safety Observation"
]
SeverityLevel = Literal["Informational", "Low", "Medium", "High", "Critical"]
ActionType = Literal["Containment", "Corrective", "Preventive", "Risk Mitigation"]
ConfidenceLevel = Literal["High", "Medium", "Low"]


class ExistingActionRef(BaseModel):
    """One action already planned/existing on a CAPA, passed to the
    Generator as dedup/build-on context. Distinct from `CAPARecord.actions`
    (the Evaluator's ad-hoc single-action-text field, a different meaning —
    see phases/phase3.md Sub-Phase 3b decision 5)."""

    type: ActionType
    description: str


class CAPARecord(BaseModel):
    """Entry payload from SoapBox — single input for every AI endpoint
    (generate/evaluate/improve/explain). Distinct from `Capa` (the mirrored
    DB row): this is what the UI sends in, not what's stored."""

    tenant_id: str
    capa_id: str
    title: str
    description: str
    source_module: SourceModule
    source_record_id: Optional[str] = None
    site_id: Optional[str] = None
    owner_group_id: Optional[str] = None
    severity: Optional[SeverityLevel] = None
    priority: Optional[SeverityLevel] = None
    due_date: Optional[date] = None
    capa_type: Optional[ActionType] = None
    root_cause_statement: Optional[str] = None
    rca_method: Optional[str] = None
    contributing_factors: Optional[list[str]] = None
    failed_controls: Optional[list[str]] = None
    missing_controls: Optional[list[str]] = None
    root_cause_category: Optional[str] = None
    actions: Optional[list[str]] = None
    existing_actions: Optional[list[ExistingActionRef]] = None  # Generator only — see phases/phase3.md Sub-Phase 3b decision 5
    requested_action_type: Optional[ActionType] = None  # Generator only
    num_actions: Optional[int] = None  # Generator only: 1-3, defaults to 2
    edit_instruction: Optional[str] = None  # Improver only
    action_id: Optional[str] = None  # Evaluator only — see phases/phase4.md decision 1


class SimilarCapaSummary(BaseModel):
    capa_id: str
    title: str
    root_cause_summary: str
    action_summary: str
    action_type: str
    effectiveness_result: Optional[str] = None
    site_id: str
    group_id: str
    root_cause_category: Optional[str] = None
    similarity_score: Optional[float] = None


class EffectiveActionSummary(BaseModel):
    action_type: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    effectiveness_result: Optional[str] = None
    evidence_required: Optional[list[str]] = None
    root_cause_category: Optional[str] = None
    site_id: Optional[str] = None
    group_id: Optional[str] = None


class SopExcerpt(BaseModel):
    id: str
    title: str
    excerpt: str
    relevance_score: Optional[float] = None


class RegulatoryExcerpt(BaseModel):
    id: str
    title: str
    excerpt: str
    relevance_score: Optional[float] = None


class InferredField(BaseModel):
    value: Any
    source: Literal["inferred"] = "inferred"
    confidence: float


class NL2SQLResult(BaseModel):
    """Result of one guarded NL2SQL query (retrieval/nl2sql.py). `rows`'
    shape varies with whatever whitelisted SELECT the LLM generated — kept as
    list[dict] as a documented exception (see phases/phase2.md decision 2);
    every other ContextPackage field is fully typed."""

    question: str
    sql: str
    row_count: int
    rows: list[dict[str, Any]]


class ContextPackage(BaseModel):
    """Output of the Context Retrieval Agent. Every downstream agent
    consumes only this — never raw DB/vector-store results directly."""

    problem_summary: str
    root_cause: Optional[str] = None
    root_cause_category: Optional[str] = None
    severity: Optional[str] = None
    site_id: Optional[str] = None
    owner_group_id: Optional[str] = None
    similar_capas: list[SimilarCapaSummary] = []
    similar_capas_is_fallback: bool = False
    effective_actions: list[EffectiveActionSummary] = []
    relevant_sops: list[SopExcerpt] = []
    regulatory_context: list[RegulatoryExcerpt] = []
    missing_fields: list[str] = []
    inferred_fields: dict[str, InferredField] = {}
    enterprise_context: list[NL2SQLResult] = []


class AgentInput(BaseModel):
    capa_input: CAPARecord
    context_package: ContextPackage
    action_type: Optional[str] = None  # Generator only
    action_text: Optional[str] = None  # Evaluator only — resolved action text to score


# =============================================================================
# Phase 3 — Generator agent contracts. See phases/phase3.md decision 1: built
# against reference/backend's actual end-state (requirements/options), not
# overview.md's older flat per-action shape.
# =============================================================================

class ActionOption(BaseModel):
    text: str


class ActionRequirement(BaseModel):
    """One underlying need an action must satisfy. Exactly one option if
    there's genuinely only one valid way to satisfy it (mandatory); 2-5
    meaningfully different options if there are legitimate alternatives."""

    label: str
    mandatory: bool
    options: list[ActionOption]

    @model_validator(mode="after")
    def _check_option_count(self) -> "ActionRequirement":
        n = len(self.options)
        if self.mandatory and n != 1:
            raise ValueError(f"mandatory requirement {self.label!r} must have exactly 1 option, got {n}")
        if not self.mandatory and not (2 <= n <= 5):
            raise ValueError(f"optional requirement {self.label!r} must have 2-5 options, got {n}")
        return self


class ActionSkeleton(BaseModel):
    """Generator step 1 output (skeleton.jinja2) — decides WHAT the action
    is. No due-date/evidence/effectiveness-check/confidence yet; those need
    the heavy historical/SOP/regulatory context that step 2 (enrich) uses.
    See phases/phase3.md Sub-Phase 3b decision 1."""

    type: ActionType
    title: str
    requirements: list[ActionRequirement]
    linked_root_cause: str
    rationale: str

    @field_validator("requirements")
    @classmethod
    def _at_least_one_requirement(cls, v: list[ActionRequirement]) -> list[ActionRequirement]:
        if not v:
            raise ValueError("requirements must have at least 1 entry")
        return v

    @field_validator("rationale")
    @classmethod
    def _rationale_is_short(cls, v: str) -> str:
        if len(v) > 400:
            raise ValueError(f"rationale must be 1-2 concise sentences (<=400 chars), got {len(v)}")
        return v


class ActionEnrichment(BaseModel):
    """Generator step 2 output (enrich.jinja2) — adds the operational
    details that need similar_capas/effective_actions/SOPs/regulatory/
    enterprise context. Merged with its matching ActionSkeleton (by index)
    into a GeneratedAction."""

    recommended_owner_role: str
    recommended_due_date: date
    required_evidence: list[str]
    effectiveness_check_method: str
    confidence_level: ConfidenceLevel
    similar_capa_reference: Optional[str] = None

    @field_validator("required_evidence")
    @classmethod
    def _min_two_evidence_items(cls, v: list[str]) -> list[str]:
        if len(v) < 2:
            raise ValueError(f"required_evidence must have at least 2 items, got {len(v)}")
        return v


class GeneratedAction(BaseModel):
    """One action from the Generator (1-3 returned per call) — the merge of
    one ActionSkeleton + its matching ActionEnrichment."""

    type: ActionType
    title: str
    requirements: list[ActionRequirement]
    recommended_owner_role: str
    recommended_due_date: date
    required_evidence: list[str]
    effectiveness_check_method: str
    rationale: str
    linked_root_cause: str
    confidence_level: ConfidenceLevel
    similar_capa_reference: Optional[str] = None

    @field_validator("requirements")
    @classmethod
    def _at_least_one_requirement(cls, v: list[ActionRequirement]) -> list[ActionRequirement]:
        if not v:
            raise ValueError("requirements must have at least 1 entry")
        return v

    @field_validator("required_evidence")
    @classmethod
    def _min_two_evidence_items(cls, v: list[str]) -> list[str]:
        if len(v) < 2:
            raise ValueError(f"required_evidence must have at least 2 items, got {len(v)}")
        return v


class ActionTaxonomyEntry(BaseModel):
    """CAPA_AI_ACTION_TAXONOMY row — action_type x theme reference data used
    only to steer Generator variety. See phases/phase3.md decision 2."""

    action_taxonomy_id: str
    action_type: str
    theme: str
    description: Optional[str] = None


class GenerateActionsResponse(BaseModel):
    request_id: str
    capa_id: str
    action_type: str
    actions: list[GeneratedAction]
    model_version: str


# =============================================================================
# Phase 4 — Evaluator / Scoring Engine contracts. See phases/phase4.md.
# LLM never scores: it only classifies (action_theme) and judges one semantic
# fact (addresses_root_cause) or wording quality (clarity/specificity). Every
# `passed` bool either comes from Layer 1 regex or is derived in Python from
# the classification + config.py's taxonomy/category tables.
# =============================================================================

ActionTheme = Literal[
    "SOP Update",
    "Engineering Control",
    "Signage",
    "PPE",
    "Training",
    "Inspection Cadence",
    "Maintenance Schedule",
    "Process Change",
    "Personnel Change",
    "System/Software Control",
]

WeaknessLevel = Literal["None", "Low", "Medium", "High", "Critical"]


class DimensionResult(BaseModel):
    passed: bool
    reason: str


class EvaluationResult(BaseModel):
    """One DimensionResult per scoring dimension. Field order/names must
    exactly match config.DIMENSION_WEIGHTS' keys — ALL_DIMENSIONS below is
    the single source of truth other modules import instead of redeclaring
    this list (avoids the reference's analysis.md-flagged duplication bug)."""

    clarity: DimensionResult
    specificity: DimensionResult
    root_cause_linkage: DimensionResult
    preventive_value: DimensionResult
    ownership: DimensionResult
    due_date_quality: DimensionResult
    evidence_requirement: DimensionResult
    effectiveness_check: DimensionResult
    # Inverted semantics: passed=True means the action has a systemic/
    # non-training component (or training is genuinely sufficient for this
    # root-cause category) — passed=False means it is training-only where
    # that's not enough. See config.TRAINING_SUFFICIENT_CATEGORIES.
    training_overreliance: DimensionResult


ALL_DIMENSIONS = list(EvaluationResult.model_fields.keys())


class RecurrenceResult(BaseModel):
    recurrence_detected: bool
    prior_occurrence_count: int
    recurred_at_same_site: bool = False
    past_actions_were_effective: Optional[bool] = None
    new_actions_are_same_as_past: Optional[bool] = None
    recurrence_warning: Optional[str] = None


class ScoringResult(BaseModel):
    score: int  # 0-100
    weakness_level: WeaknessLevel
    failed_dimensions: list[str]
    recurrence: RecurrenceResult


class EvaluateActionResponse(BaseModel):
    request_id: str
    capa_id: str
    action_id: Optional[str] = None
    score: int
    weakness_level: WeaknessLevel
    evaluation: EvaluationResult
    recurrence: RecurrenceResult
    failed_dimensions: list[str]
    model_version: str


# =============================================================================
# Phase 5 — Improver agent contracts. See phases/phase5.md decision 2: input
# and output both flat text (same shape as the Evaluator), not
# requirements/options — the Improver is decoupled from the Generator's
# structured schema for the same reason the Evaluator is.
# =============================================================================

class ImproverResult(BaseModel):
    original_action_text: str
    improved_action_title: str
    improved_action_description: str
    changes_explained: list[str]
    # Populated only when Python (not the LLM) decides the original action
    # can't structurally cover the root cause alone — see phases/phase5.md
    # Sub-Phase 5b decision 1. Reuses the Generator's GeneratedAction shape
    # per that decision's follow-up question, capped at 2.
    additional_actions: list[GeneratedAction] = []

    @field_validator("changes_explained")
    @classmethod
    def _at_least_one_change(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("changes_explained must have at least 1 entry")
        return v


class ImproveActionResponse(BaseModel):
    request_id: str
    capa_id: str
    action_id: Optional[str] = None
    original_action_text: str
    improved_action_title: str
    improved_action_description: str
    changes_explained: list[str]
    additional_actions: list[GeneratedAction] = []
    model_version: str


# =============================================================================
# Phase 6 — Explainability agent contract. The agent itself returns a plain
# `str` (see phases/phase6.md decision 3 — nothing structured to validate),
# this envelope is the only schema for it, applied at the HTTP boundary.
# =============================================================================

class ExplainActionResponse(BaseModel):
    request_id: str
    capa_id: str
    action_id: Optional[str] = None
    explanation: str
    score: int
    weakness_level: WeaknessLevel
    model_version: str


# =============================================================================
# Phase 7 — read endpoints. Composition of existing repository-layer schemas
# (Capa/CapaAction/CapaRCA/AuditTrailEntry) — no new domain schema needed,
# only response envelopes. See phases/phase7.md decision 5.
# =============================================================================

class CapaDetailResponse(BaseModel):
    capa: Capa
    actions: list[CapaAction] = []
    rca: Optional[CapaRCA] = None


class CapaListResponse(BaseModel):
    items: list[Capa]
    total: int
    limit: int
    offset: int


class AuditTrailListResponse(BaseModel):
    items: list[AuditTrailEntry]
    total: int
    limit: int
    offset: int
