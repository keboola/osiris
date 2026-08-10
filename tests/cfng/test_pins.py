"""Pins are computed from the REST tool manifest and drift is classified."""

from osiris.cfng.pins import DriftKind, detect_tool_drift, tool_pin


def test_pin_hashes_input_and_output_schema():
    pin = tool_pin({"name": "search", "inputSchema": {"type": "object"}, "outputSchema": {"type": "array"}})
    assert pin.input.startswith("sha256:")
    assert pin.output.startswith("sha256:")


def test_pin_is_key_order_independent():
    a = tool_pin({"name": "s", "inputSchema": {"a": 1, "b": 2}})
    b = tool_pin({"name": "s", "inputSchema": {"b": 2, "a": 1}})
    assert a.input == b.input


def test_pin_ignores_description_and_title_churn():
    """Only the contract matters — prose changes must not look like drift."""
    a = tool_pin({"name": "s", "description": "old", "title": "A", "inputSchema": {"x": 1}})
    b = tool_pin({"name": "s", "description": "new wording", "title": "B", "inputSchema": {"x": 1}})
    assert a.input == b.input


def test_absent_output_schema_pins_to_none():
    assert tool_pin({"name": "s", "inputSchema": {}}).output is None


def test_no_drift_when_identical():
    pinned = {"imdb__search": tool_pin({"name": "search", "inputSchema": {"x": 1}})}
    assert detect_tool_drift(pinned, dict(pinned)) == []


def test_changed_input_schema_is_tool_contract_drift():
    pinned = {"imdb__search": tool_pin({"name": "search", "inputSchema": {"required": ["title"]}})}
    live = {"imdb__search": tool_pin({"name": "search", "inputSchema": {"required": ["title", "region"]}})}
    drifts = detect_tool_drift(pinned, live)
    assert len(drifts) == 1
    assert drifts[0].kind is DriftKind.TOOL_CONTRACT
    assert drifts[0].subject == "imdb__search"


def test_missing_tool_is_drift():
    pinned = {"imdb__search": tool_pin({"name": "search", "inputSchema": {}})}
    drifts = detect_tool_drift(pinned, {})
    assert len(drifts) == 1
    assert "missing" in drifts[0].diff


def test_extra_live_tool_is_not_drift():
    """A connector gaining tools does not break a plan that does not use them."""
    pinned = {"imdb__search": tool_pin({"name": "search", "inputSchema": {}})}
    live = dict(pinned) | {"imdb__other": tool_pin({"name": "other", "inputSchema": {}})}
    assert detect_tool_drift(pinned, live) == []
