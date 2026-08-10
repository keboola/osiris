"""Canonical serialization must be stable regardless of input key order."""

import pytest

from osiris.determinism.canonical import canonical_bytes, canonical_json, canonical_yaml


def test_json_sorts_keys_recursively():
    assert canonical_json({"z": 1, "a": {"y": 2, "b": 3}}) == '{"a":{"b":3,"y":2},"z":1}'


def test_json_is_order_independent():
    assert canonical_json({"a": 1, "b": 2}) == canonical_json({"b": 2, "a": 1})


def test_json_preserves_list_order():
    assert canonical_json({"k": [3, 1, 2]}) == '{"k":[3,1,2]}'


def test_json_keeps_bool_distinct_from_int():
    assert canonical_json({"a": True, "b": 1}) == '{"a":true,"b":1}'


def test_json_keeps_unicode_unescaped():
    assert canonical_json({"k": "přehled"}) == '{"k":"přehled"}'


def test_yaml_has_explicit_markers_and_sorted_keys():
    assert canonical_yaml({"z": 1, "a": 2}) == "---\na: 2\nz: 1\n...\n"


def test_bytes_are_utf8_of_json():
    assert canonical_bytes({"k": "á"}) == '{"k":"á"}'.encode()


def test_bytes_rejects_unknown_format():
    with pytest.raises(ValueError, match="Unknown format: toml"):
        canonical_bytes({}, fmt="toml")
