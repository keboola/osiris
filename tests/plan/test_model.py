"""The plan model is strict and its fingerprint excludes ephemeral fields."""

from pydantic import ValidationError
import pytest

from osiris.plan.model import DriftAction, Plan, Policy, Step


def _plan(**overrides) -> Plan:
    base = {
        "metadata": {"name": "demo", "generated_at": "2026-08-10T14:00:00Z"},
        "pins": {"cfng": {"proxy": "p", "catalog_version": "sha256:1a"}, "tools": {}},
        "policy": {},
        "params": {},
        "steps": [{"id": "a", "uses": "cfng_call", "with": {"connector": "imdb", "tool": "search"}}],
        "fingerprints": {},
    }
    return Plan(**(base | overrides))


def test_step_accepts_with_as_a_field_name():
    step = Step(id="a", uses="cfng_call", **{"with": {"k": 1}})
    assert step.with_ == {"k": 1}


def test_policy_defaults_fail_on_contract_and_warn_on_catalog():
    p = Policy()
    assert p.on_tool_contract_drift is DriftAction.FAIL
    assert p.on_catalog_drift is DriftAction.WARN
    assert p.on_proxy_scope_drift is DriftAction.WARN


def test_duplicate_step_ids_are_rejected():
    with pytest.raises(ValidationError, match="duplicate step id"):
        _plan(
            steps=[
                {"id": "a", "uses": "cfng_call", "with": {}},
                {"id": "a", "uses": "sql", "with": {}},
            ]
        )


def test_empty_steps_are_rejected():
    with pytest.raises(ValidationError, match="at least one step"):
        _plan(steps=[])


def test_unknown_step_type_is_rejected():
    with pytest.raises(ValidationError, match="unknown step type"):
        _plan(steps=[{"id": "a", "uses": "wat", "with": {}}])


def test_canonical_excludes_fingerprints_and_generated_at():
    """Two plans differing only in ephemeral fields must canonicalize identically."""
    a = _plan()
    b = _plan(metadata={"name": "demo", "generated_at": "2099-01-01T00:00:00Z"})
    b.fingerprints = {"plan": "sha256:deadbeef"}
    assert a.canonical_without_fingerprints() == b.canonical_without_fingerprints()


def test_canonical_changes_when_a_step_changes():
    a = _plan()
    b = _plan(steps=[{"id": "a", "uses": "cfng_call", "with": {"connector": "imdb", "tool": "other"}}])
    assert a.canonical_without_fingerprints() != b.canonical_without_fingerprints()
