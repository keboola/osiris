"""The plan model is strict and its fingerprint excludes ephemeral fields."""

from datetime import UTC, datetime
from decimal import Decimal

from pydantic import ValidationError
import pytest

from osiris.plan.model import DriftAction, NonJsonValue, Plan, Policy, Step, reject_non_json_values


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


# --- The JSON value domain -------------------------------------------------
#
# A plan's hash is only a fact about its meaning when the plan has exactly one
# serialization. Every type below has more than one, or none, so each is refused
# rather than coerced into whichever one this process happened to pick.

JSON_VALUES = [
    "text",
    "",
    0,
    -17,
    7.5,
    -1e300,
    True,
    False,
    None,
    [],
    [1, "two", None, [3.0], {"k": False}],
    {},
    {"a": {"b": [{"c": 1}]}},
]


@pytest.mark.parametrize("value", JSON_VALUES)
def test_json_values_are_accepted(value):
    reject_non_json_values({"params": {"v": value}})


NON_JSON_VALUES = [
    # (value, type name the message must contain)
    ({"a", "b"}, "set"),
    (frozenset({"a"}), "frozenset"),
    (("a", "b"), "tuple"),
    (b"bytes", "bytes"),
    (bytearray(b"x"), "bytearray"),
    (Decimal("1.0"), "Decimal"),
    (datetime(2026, 8, 10, tzinfo=UTC), "datetime"),
    (object(), "object"),
]


@pytest.mark.parametrize(("value", "type_name"), NON_JSON_VALUES)
def test_non_json_types_are_rejected_and_named(value, type_name):
    with pytest.raises(NonJsonValue) as excinfo:
        reject_non_json_values({"params": {"tags": value}})
    assert excinfo.value.path == "params.tags"
    assert type_name in str(excinfo.value)


NON_FINITE_FLOATS = [
    (float("nan"), "NaN"),
    (float("inf"), "Infinity"),
    (float("-inf"), "-Infinity"),
]


@pytest.mark.parametrize(("value", "name"), NON_FINITE_FLOATS)
def test_non_finite_floats_are_rejected_and_named(value, name):
    """`json.loads` accepts these literals and pydantic then rewrites all three to null."""
    with pytest.raises(NonJsonValue) as excinfo:
        reject_non_json_values({"params": {"ratio": value}})
    assert excinfo.value.path == "params.ratio"
    assert name in str(excinfo.value)


@pytest.mark.parametrize("key", [1, 1.5, None, True, ("a",)])
def test_non_string_object_keys_are_rejected(key):
    """A non-string key is coerced to one, at which point it collides with the real string key."""
    with pytest.raises(NonJsonValue, match="not a string"):
        reject_non_json_values({"params": {key: "v"}})


def test_the_reported_path_locates_the_value_inside_lists_and_steps():
    with pytest.raises(NonJsonValue) as excinfo:
        reject_non_json_values({"steps": [{"id": "a", "with": {"rows": [1, {"bad": {"x"}}]}}]})
    assert excinfo.value.path == "steps[0].with.rows[1].bad"


def test_a_bare_offending_value_is_reported_against_the_plan():
    with pytest.raises(NonJsonValue) as excinfo:
        reject_non_json_values({"a"})
    assert excinfo.value.path == "<plan>"


def test_the_model_refuses_a_set_that_reached_it_through_yaml():
    """`yaml.safe_load` on a `!!set` tag materializes a real set, so the model checks too.

    Without this the hash of a hand-edited `manifest.yaml` would differ in every
    process that loaded it, which is the same defect as the freeze-time one at a
    different door.
    """
    with pytest.raises(ValidationError, match="params.tags"):
        _plan(params={"tags": {"alpha", "beta"}})


def test_the_model_refuses_a_nan_that_reached_it_through_json():
    with pytest.raises(ValidationError, match="NaN"):
        _plan(params={"ratio": float("nan")})


def test_a_tuple_is_not_silently_accepted_as_a_list():
    """Pydantic would coerce it; then nothing downstream could tell the two apart."""
    with pytest.raises(ValidationError, match="tuple"):
        _plan(params={"tags": ("alpha", "beta")})


# --- Unknown fields --------------------------------------------------------


def test_an_unknown_plan_field_is_rejected_rather_than_dropped():
    """Under `extra="ignore"` this froze to the same hash as a plan without it."""
    with pytest.raises(ValidationError, match="retries"):
        _plan(retries=5)


def test_an_unknown_step_field_is_rejected():
    with pytest.raises(ValidationError, match="timeout"):
        _plan(steps=[{"id": "a", "uses": "sql", "with": {}, "timeout": 30}])


def test_an_unknown_policy_field_is_rejected():
    with pytest.raises(ValidationError, match="on_weather_drift"):
        _plan(policy={"on_weather_drift": "fail"})


def test_the_declared_fields_still_round_trip_under_forbid():
    """`extra="forbid"` must not break reloading what freeze itself wrote."""
    plan = _plan()
    reloaded = Plan(**plan.model_dump(by_alias=True, mode="json"))
    assert reloaded.canonical_without_fingerprints() == plan.canonical_without_fingerprints()
    # The wire name is what the manifest carries, so it is what must be accepted.
    assert "with" in plan.model_dump(by_alias=True)["steps"][0]
