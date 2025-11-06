"""Tests for Supabase writer replace semantics and DDL policy."""

from types import SimpleNamespace

import pandas as pd
import pytest

import osiris.drivers.supabase_writer_driver as supabase_driver

pytestmark = pytest.mark.supabase


class FakeTable:
    def __init__(self):
        self.operations = []

    def select(self, *_args, **_kwargs):
        return SimpleNamespace(data=[])

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        return SimpleNamespace(data=[])

    def insert(self, *_args, **_kwargs):
        self.operations.append("insert")
        return self

    def upsert(self, *_args, **_kwargs):
        self.operations.append("upsert")
        return self

    def delete(self):
        return self

    def in_(self, *_args, **_kwargs):
        return self

    def neq(self, *_args, **_kwargs):
        return self


class FakeSupabaseClient:
    def __init__(self, *_args, **_kwargs):
        self.table_ref = FakeTable()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def table(self, _name):
        return self.table_ref


def test_replace_mode_invokes_cleanup(monkeypatch):
    driver = supabase_driver.SupabaseWriterDriver()

    df = pd.DataFrame({"id": [1, 2], "value": [10, 20]})

    cleanup_args = {}

    def fake_cleanup(**kwargs):
        cleanup_args.update(kwargs)

    monkeypatch.setattr(supabase_driver, "SupabaseClient", FakeSupabaseClient)
    monkeypatch.setattr(driver, "_table_exists", lambda client, table: True)
    monkeypatch.setattr(driver, "_perform_replace_cleanup", fake_cleanup)

    result = driver.run(
        step_id="replace-test",
        config={
            "resolved_connection": {"sql_url": "https://sql.example"},
            "table": "demo",
            "write_mode": "replace",
            "primary_key": ["id"],
            "ddl_channel": "http_sql",
        },
        inputs={"df_upstream": df},
        ctx=None,
    )

    assert result == {}
    assert cleanup_args["primary_key"] == ["id"]
    assert cleanup_args["primary_key_values"] == [(1,), (2,)]
