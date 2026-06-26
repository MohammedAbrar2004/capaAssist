"""Pure unit tests for agents/generator.py's skeleton/enrich 2-call flow +
the ActionSkeleton/ActionEnrichment/ActionRequirement validators in
models/schemas.py — no network, no DB. See phases/phase3.md Sub-Phase 3b.
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

import agents.generator as generator_mod  # noqa: E402
from models.schemas import ActionEnrichment, ActionRequirement, ActionSkeleton, GeneratedAction  # noqa: E402


def _skeleton(**overrides) -> dict:
    base = dict(
        type="Corrective",
        title="Replace failed wire rope",
        requirements=[
            {"label": "Eliminate hazard", "mandatory": True, "options": [{"text": "Replace the rope."}]}
        ],
        linked_root_cause="Wire rope inspection criteria not specified",
        rationale="Replacing the rope removes the immediate hazard.",
    )
    base.update(overrides)
    return base


def _enrichment(**overrides) -> dict:
    base = dict(
        recommended_owner_role="Maintenance Supervisor",
        recommended_due_date=(date.today() + timedelta(days=45)).isoformat(),
        required_evidence=["Work order", "Inspection record"],
        effectiveness_check_method="Re-inspection at 30 days",
        confidence_level="High",
        similar_capa_reference=None,
    )
    base.update(overrides)
    return base


# --- ActionRequirement validators (unchanged from Phase 3a) -----------------

def test_mandatory_requirement_must_have_exactly_one_option():
    ActionRequirement(label="x", mandatory=True, options=[{"text": "a"}])
    with pytest.raises(ValidationError):
        ActionRequirement(label="x", mandatory=True, options=[{"text": "a"}, {"text": "b"}])


@pytest.mark.parametrize("n", [2, 3, 5])
def test_optional_requirement_accepts_two_to_five_options(n):
    ActionRequirement(label="x", mandatory=False, options=[{"text": str(i)} for i in range(n)])


@pytest.mark.parametrize("n", [0, 1, 6])
def test_optional_requirement_rejects_outside_two_to_five(n):
    with pytest.raises(ValidationError):
        ActionRequirement(label="x", mandatory=False, options=[{"text": str(i)} for i in range(n)])


# --- ActionSkeleton validators ------------------------------------------------

def test_skeleton_requires_at_least_one_requirement():
    with pytest.raises(ValidationError):
        ActionSkeleton.model_validate(_skeleton(requirements=[]))


def test_skeleton_rationale_must_be_short():
    with pytest.raises(ValidationError, match="1-2 concise sentences"):
        ActionSkeleton.model_validate(_skeleton(rationale="x" * 401))


def test_skeleton_valid_case():
    sk = ActionSkeleton.model_validate(_skeleton())
    assert sk.type == "Corrective"


# --- ActionEnrichment validators ---------------------------------------------

def test_enrichment_requires_min_two_evidence_items():
    with pytest.raises(ValidationError):
        ActionEnrichment.model_validate(_enrichment(required_evidence=["only one"]))


def test_enrichment_valid_case():
    en = ActionEnrichment.model_validate(_enrichment())
    assert en.confidence_level == "High"


# --- _validate_due_date_windows (now reading config.DUE_DATE_WINDOWS) -------

@pytest.mark.parametrize(
    "action_type,days_out,should_pass",
    [
        ("Containment", 3, True),
        ("Containment", 8, False),
        ("Corrective", 60, True),
        ("Corrective", 10, False),
        ("Preventive", 120, True),
        ("Preventive", 30, False),
        ("Risk Mitigation", 30, True),
        ("Risk Mitigation", 90, False),
    ],
)
def test_due_date_windows(action_type, days_out, should_pass):
    due = date.today() + timedelta(days=days_out)
    action = GeneratedAction.model_validate({**_skeleton(type=action_type), **_enrichment(recommended_due_date=due.isoformat())})
    if should_pass:
        generator_mod._validate_due_date_windows([action])
    else:
        with pytest.raises(ValueError, match="Due date window violation"):
            generator_mod._validate_due_date_windows([action])


# --- _parse_skeletons / _parse_enrichments -----------------------------------

def test_parse_skeletons_overwrites_mismatched_type():
    raw = json.dumps([_skeleton(type="Preventive")])
    skeletons = generator_mod._parse_skeletons(raw, "Corrective")
    assert skeletons[0].type == "Corrective"


def test_parse_skeletons_rejects_non_array():
    raw = json.dumps(_skeleton())
    with pytest.raises(ValueError, match="Expected JSON array"):
        generator_mod._parse_skeletons(raw, "Corrective")


def test_parse_enrichments_rejects_length_mismatch():
    raw = json.dumps([_enrichment(), _enrichment()])
    with pytest.raises(ValueError, match="Expected 1 enrichment"):
        generator_mod._parse_enrichments(raw, expected_len=1)


def test_parse_enrichments_accepts_matching_length():
    raw = json.dumps([_enrichment()])
    result = generator_mod._parse_enrichments(raw, expected_len=1)
    assert len(result) == 1


# --- run() — 2-call flow (mocked call_llm, no network) -----------------------

class _FakeRepo:
    def fetch_action_taxonomy(self, action_type):
        return []


@pytest.fixture
def agent_input():
    from models.schemas import AgentInput, CAPARecord, ContextPackage, ExistingActionRef

    return AgentInput(
        capa_input=CAPARecord(
            tenant_id="TENANT_ACERTECH",
            capa_id="CAPA_TEST",
            title="Test",
            description="Test description",
            source_module="Incident",
            existing_actions=[ExistingActionRef(type="Corrective", description="Replace the rope")],
        ),
        context_package=ContextPackage(problem_summary="Test description"),
        action_type="Preventive",
    )


@pytest.mark.asyncio
async def test_run_makes_two_calls_in_order(agent_input, monkeypatch):
    calls = []

    async def fake_call_llm(messages, model, temperature, max_tokens=None):
        calls.append(messages[-1]["content"])
        if len(calls) == 1:
            return json.dumps([_skeleton(type="Preventive")])
        return json.dumps([_enrichment(recommended_due_date=(date.today() + timedelta(days=90)).isoformat())])

    monkeypatch.setattr(generator_mod, "call_llm", fake_call_llm)
    actions = await generator_mod.run(agent_input, _FakeRepo(), num_actions=1)

    assert len(calls) == 2
    assert len(actions) == 1
    assert actions[0].type == "Preventive"
    # skeleton call doesn't see historical context section; enrich call does
    assert "DECOMPOSING THE ACTION" in calls[0]
    assert "ACTION(S) TO ENRICH" in calls[1]


@pytest.mark.asyncio
async def test_run_existing_actions_rendered_in_skeleton_prompt(agent_input, monkeypatch):
    captured = {}

    async def fake_call_llm(messages, model, temperature, max_tokens=None):
        if "prompt" not in captured:
            captured["prompt"] = messages[-1]["content"]
            return json.dumps([_skeleton(type="Preventive")])
        return json.dumps([_enrichment(recommended_due_date=(date.today() + timedelta(days=90)).isoformat())])

    monkeypatch.setattr(generator_mod, "call_llm", fake_call_llm)
    await generator_mod.run(agent_input, _FakeRepo(), num_actions=1)

    assert "Replace the rope" in captured["prompt"]
    assert "[Corrective]" in captured["prompt"]


@pytest.mark.asyncio
async def test_run_retries_skeleton_once_then_succeeds(agent_input, monkeypatch):
    calls = {"n": 0}

    async def fake_call_llm(messages, model, temperature, max_tokens=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return "not valid json"
        if calls["n"] == 2:
            return json.dumps([_skeleton(type="Preventive")])
        return json.dumps([_enrichment(recommended_due_date=(date.today() + timedelta(days=90)).isoformat())])

    monkeypatch.setattr(generator_mod, "call_llm", fake_call_llm)
    actions = await generator_mod.run(agent_input, _FakeRepo(), num_actions=1)
    assert len(actions) == 1
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_run_retries_enrich_on_length_mismatch(agent_input, monkeypatch):
    calls = {"n": 0}

    async def fake_call_llm(messages, model, temperature, max_tokens=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return json.dumps([_skeleton(type="Preventive")])
        if calls["n"] == 2:
            d90 = (date.today() + timedelta(days=90)).isoformat()
            return json.dumps([_enrichment(recommended_due_date=d90), _enrichment(recommended_due_date=d90)])  # wrong length (2 != 1)
        return json.dumps([_enrichment(recommended_due_date=(date.today() + timedelta(days=90)).isoformat())])

    monkeypatch.setattr(generator_mod, "call_llm", fake_call_llm)
    actions = await generator_mod.run(agent_input, _FakeRepo(), num_actions=1)
    assert len(actions) == 1
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_run_raises_after_two_skeleton_failures(agent_input, monkeypatch):
    async def fake_call_llm(messages, model, temperature, max_tokens=None):
        return "still not valid json"

    monkeypatch.setattr(generator_mod, "call_llm", fake_call_llm)
    with pytest.raises(ValueError, match="Generator failed after 2 attempts"):
        await generator_mod.run(agent_input, _FakeRepo(), num_actions=1)
