"""Shared fixtures for unit tests."""

import pytest

from osiris.core.compiler_v0 import CompilerV0
from osiris.core.fs_config import load_osiris_config
from osiris.core.fs_paths import FilesystemContract


@pytest.fixture
def compiler_instance(tmp_path):
    """Create a CompilerV0 instance with minimal filesystem contract."""
    # Create minimal osiris.yaml
    osiris_yaml = tmp_path / "osiris.yaml"
    osiris_yaml.write_text(
        """
version: "2.0"
filesystem:
  base_path: "."
  run_logs: "run_logs"
  compilations: ".osiris/index/compilations"
  outputs:
    directory: "output"
"""
    )

    # Load config and create contract
    fs_config, ids_config, raw_config = load_osiris_config(osiris_yaml)
    contract = FilesystemContract(fs_config, ids_config)

    # Create compiler instance
    return CompilerV0(fs_contract=contract, pipeline_slug="test-pipeline")
