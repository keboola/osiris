"""Pins are computed from the REST tool manifest and drift is classified."""

from osiris.cfng.pins import DriftKind, detect_pin_key_collisions, detect_tool_drift, pin_key, tool_pin


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


# --- outputSchema, both directions -------------------------------------------
# The asymmetry these cover was the HIGH defect: `want.output is not None`
# meant a pin recording `output: null` could never drift, so a tool that
# *gained* an output contract after freeze ran as if nothing had happened.


def test_added_output_schema_is_drift():
    """A tool that gains an outputSchema after freeze has changed its contract."""
    pinned = {"imdb__search": tool_pin({"name": "search", "inputSchema": {"x": 1}})}
    live = {"imdb__search": tool_pin({"name": "search", "inputSchema": {"x": 1}, "outputSchema": {"type": "object"}})}
    drifts = detect_tool_drift(pinned, live)
    assert len(drifts) == 1
    assert drifts[0].kind is DriftKind.TOOL_CONTRACT
    assert "outputSchema added since freeze" in drifts[0].diff


def test_removed_output_schema_is_drift():
    pinned = {"imdb__search": tool_pin({"name": "search", "inputSchema": {"x": 1}, "outputSchema": {"type": "object"}})}
    live = {"imdb__search": tool_pin({"name": "search", "inputSchema": {"x": 1}})}
    drifts = detect_tool_drift(pinned, live)
    assert len(drifts) == 1
    assert "outputSchema removed since freeze" in drifts[0].diff


def test_replaced_output_schema_is_drift():
    pinned = {"imdb__search": tool_pin({"name": "search", "inputSchema": {}, "outputSchema": {"type": "object"}})}
    live = {"imdb__search": tool_pin({"name": "search", "inputSchema": {}, "outputSchema": {"type": "array"}})}
    drifts = detect_tool_drift(pinned, live)
    assert len(drifts) == 1
    assert "outputSchema changed since freeze" in drifts[0].diff


def test_unchanged_null_output_schema_is_not_drift():
    """Symmetry must not turn "both sides have none" into a false positive."""
    pinned = {"imdb__search": tool_pin({"name": "search", "inputSchema": {"x": 1}})}
    live = {"imdb__search": tool_pin({"name": "search", "inputSchema": {"x": 1}})}
    assert detect_tool_drift(pinned, live) == []


def test_both_halves_of_a_moved_contract_are_reported():
    pinned = {"imdb__search": tool_pin({"name": "search", "inputSchema": {"x": 1}, "outputSchema": {"type": "object"}})}
    live = {"imdb__search": tool_pin({"name": "search", "inputSchema": {"x": 2}, "outputSchema": {"type": "array"}})}
    diffs = [d.diff for d in detect_tool_drift(pinned, live)]
    assert any("inputSchema changed" in d for d in diffs)
    assert any("outputSchema changed" in d for d in diffs)


# --- pin key collisions -------------------------------------------------------


def test_distinct_pairs_that_share_a_key_are_reported():
    """(x, y__z) and (x__y, z) flatten to the same key and must not pass silently."""
    collisions = detect_pin_key_collisions([("x", "y__z"), ("x__y", "z")])
    assert len(collisions) == 1
    assert collisions[0].key == "x__y__z"
    assert collisions[0].pairs == [("x", "y__z"), ("x__y", "z")]
    assert "ambiguous" in collisions[0].diff


def test_repeated_identical_pair_is_not_a_collision():
    """Two steps calling the same tool share a pin legitimately."""
    assert detect_pin_key_collisions([("imdb", "search"), ("imdb", "search")]) == []


def test_unambiguous_pairs_have_no_collisions():
    assert detect_pin_key_collisions([("imdb", "search"), ("imdb", "detail"), ("tmdb", "search")]) == []


def test_pin_key_matches_the_format_the_artifact_carries():
    assert pin_key("imdb", "search") == "imdb__search"
