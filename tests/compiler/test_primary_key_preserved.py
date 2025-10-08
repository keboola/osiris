"""Compiler tests for primary_key handling and invariants."""

import json


def _write_oml(path, content):
    path.write_text(content)


def test_compiler_preserves_primary_key(tmp_path, compiler_instance):
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

    success, _ = compiler_instance.compile(str(oml_path))
    assert success

    # Get paths from the filesystem contract
    paths = compiler_instance.fs_contract.manifest_paths(
        pipeline_slug=compiler_instance.pipeline_slug,
        manifest_hash=compiler_instance.manifest_hash,
        manifest_short=compiler_instance.manifest_short,
        profile=None,
    )

    config_path = paths["cfg_dir"] / "write.json"
    assert config_path.exists(), f"Config file not found at {config_path}"

    with open(config_path) as f:
        config = json.load(f)

    assert config["primary_key"] == ["id"]


def test_replace_without_primary_key_fails(tmp_path, compiler_instance):
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

    success, message = compiler_instance.compile(str(oml_path))
    assert not success
    assert "primary_key" in message.lower()
