"""enrich() — second step of the Context Retrieval Agent. LLM call (only if
a gap is actually fillable) to infer `severity` and/or `capa_type` when
missing. Every inferred value is tagged source="inferred" + a confidence
score — never silently filled. If neither field is missing, no LLM call.
"""

from typing import Optional

from pydantic import BaseModel

import config
from models.schemas import ActionType, InferredField, SeverityLevel
from services.llm import call_llm_json

_INFERABLE_FIELDS = ("severity", "capa_type")


class _EnrichmentLLMOutput(BaseModel):
    severity: Optional[SeverityLevel] = None
    severity_confidence: Optional[float] = None
    capa_type: Optional[ActionType] = None
    capa_type_confidence: Optional[float] = None


async def enrich(normalized: dict, missing_fields: list[str]) -> dict[str, InferredField]:
    needed = [f for f in _INFERABLE_FIELDS if f in missing_fields]
    if not needed:
        return {}

    prompt = (
        "Given this EHS/CAPA record, infer the following missing field(s): "
        f"{', '.join(needed)}.\n\n"
        f"Title: {normalized.get('title')}\n"
        f"Description: {normalized.get('description')}\n"
        f"Source module: {normalized.get('source_module')}\n"
        f"Root cause statement: {normalized.get('root_cause_statement') or '(none given)'}\n\n"
        "severity must be one of: Informational, Low, Medium, High, Critical.\n"
        "capa_type must be one of: Containment, Corrective, Preventive, Risk Mitigation.\n"
        "Provide a confidence score 0.0-1.0 for each field you infer."
    )
    result = await call_llm_json(
        [{"role": "user", "content": prompt}],
        config.LIGHT_MODEL,
        _EnrichmentLLMOutput,
        max_tokens=300,
    )

    inferred: dict[str, InferredField] = {}
    if "severity" in needed and result.severity is not None:
        inferred["severity"] = InferredField(
            value=result.severity, confidence=result.severity_confidence or 0.5
        )
    if "capa_type" in needed and result.capa_type is not None:
        inferred["capa_type"] = InferredField(
            value=result.capa_type, confidence=result.capa_type_confidence or 0.5
        )
    return inferred
