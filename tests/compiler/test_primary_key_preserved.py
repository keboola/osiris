"""Compiler tests for primary_key handling and invariants."""

import json

from osiris.core.compiler_v0 import CompilerV0


def _write_oml(path, content):
    path.write_text(content)


def test_compiler_preserves_primary_key(tmp_path):
    oml_path = tmp_path / "pipeline.yaml"
    _write_oml(
        oml_path,
        """
oml_version: "0.1.0"
steps:
  - id: write
    component: supabase.writer
    mode: replace
    config:
      connection: "@supabase.local"
      table: demo
      write_mode: replace
      primary_key: [id]
      ddl_channel: psycopg2
        """.strip(),
    )

    compiler = CompilerV0(output_dir=str(tmp_path / "compiled"))
    success, _ = compiler.compile(str(oml_path))
    assert success

    config_path = tmp_path / "compiled" / "cfg" / "write.json"
    with open(config_path) as f:
        config = json.load(f)

    assert config["primary_key"] == ["id"]


def test_replace_without_primary_key_fails(tmp_path):
    oml_path = tmp_path / "bad_pipeline.yaml"
    _write_oml(
        oml_path,
        """
oml_version: "0.1.0"
steps:
  - id: write
    component: supabase.writer
    mode: replace
    config:
      connection: "@supabase.local"
      table: demo
      write_mode: replace
        """.strip(),
    )

    compiler = CompilerV0(output_dir=str(tmp_path / "compiled_bad"))
    success, message = compiler.compile(str(oml_path))
    assert not success
    assert "primary_key" in message.lower()
