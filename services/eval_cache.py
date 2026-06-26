"""In-process bounded LRU cache for (EvaluationResult, RecurrenceResult) pairs.

Shared between POST /capa/evaluate (writer) and POST /capa/improve (reader)
so the Improver doesn't re-run the Evaluator when a fresh evaluation already
happened in this process. See phases/phase5.md decision 3. Not a persistence
layer — process-local only, lost on restart, never the source of truth
(that's repo.write_evaluation / capa_ai_evaluations).
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from typing import Optional

import config
from models.schemas import EvaluationResult, RecurrenceResult

CachedEval = tuple[EvaluationResult, RecurrenceResult]

_cache: "OrderedDict[str, CachedEval]" = OrderedDict()


def make_key(tenant_id: str, capa_id: str, action_id: Optional[str], action_text: str) -> str:
    suffix = action_id or hashlib.md5(action_text.encode("utf-8")).hexdigest()
    return f"{tenant_id}:{capa_id}:{suffix}"


def get(key: str) -> Optional[CachedEval]:
    if key not in _cache:
        return None
    _cache.move_to_end(key)
    return _cache[key]


def put(key: str, value: CachedEval) -> None:
    _cache[key] = value
    _cache.move_to_end(key)
    while len(_cache) > config.EVAL_CACHE_MAX_ENTRIES:
        _cache.popitem(last=False)
