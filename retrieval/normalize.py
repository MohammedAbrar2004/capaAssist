"""normalize() — pure Python, no LLM. First step of the Context Retrieval
Agent (phases/phase2.md). Maps CAPARecord fields the UI already gave us into
the working dict enrich()/retrieve() build on, and records which of the
fields a downstream agent typically needs are missing.
"""

from models.schemas import CAPARecord

# Fields whose absence should be surfaced to downstream agents/the UI —
# not an exhaustive list of every CAPARecord field, just the ones that drive
# retrieval quality or generation/evaluation reasoning.
_TRACKED_FIELDS = (
    "site_id",
    "owner_group_id",
    "severity",
    "priority",
    "due_date",
    "capa_type",
    "root_cause_statement",
    "root_cause_category",
)


def normalize(capa_input: CAPARecord) -> tuple[dict, list[str]]:
    """Returns (normalized_fields, missing_fields). normalized_fields holds
    every CAPARecord field as-is (kept, not transformed) — enrich() fills
    gaps on top of this, it doesn't second-guess what's already present."""
    normalized = capa_input.model_dump()
    missing_fields = [f for f in _TRACKED_FIELDS if normalized.get(f) is None]
    return normalized, missing_fields
