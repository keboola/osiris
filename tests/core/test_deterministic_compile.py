"""Tests for deterministic compilation behavior."""

import json
from pathlib import Path
import tempfile

import pytest
import yaml

from osiris.cli.init import init_command
from osiris.core.compiler_v0 import CompilerV0
from osiris.core.fs_config import load_osiris_config
from osiris.core.fs_paths import FilesystemContract


def test_compile_produces_deterministic_hash():
    """Test that compiling the same OML produces identical manifest hashes."""
    import os
    import shutil

    # Use project root for compilation (has components)
    project_root = Path(__file__).parent.parent.parent
    old_cwd = os.getcwd()
    try:
        os.chdir(project_root)

        # Use existing example OML that has proper components
        pipeline_file = project_root / "docs" / "examples" / "mysql_duckdb_supabase_demo.yaml"
        if not pipeline_file.exists():
            pytest.skip("Example OML not found")

        # Load filesystem contract
        fs_config, ids_config, _ = load_osiris_config()
        fs_contract = FilesystemContract(fs_config, ids_config)

        pipeline_slug = "mysql-duckdb-supabase-demo"

        # Clean up any existing builds first
        build_path = project_root / "build" / "pipelines" / "dev" / pipeline_slug
        if build_path.exists():
            shutil.rmtree(build_path)

        # Compile first time
        compiler1 = CompilerV0(fs_contract=fs_contract, pipeline_slug=pipeline_slug)
        success1, message1 = compiler1.compile(
            oml_path=str(pipeline_file),
            profile="dev",
        )
        assert success1, f"First compilation failed: {message1}"
        hash1 = compiler1.manifest_hash
        short1 = compiler1.manifest_short

        # Compile second time (small delay to ensure different timestamp)
        import time

        time.sleep(0.1)

        compiler2 = CompilerV0(fs_contract=fs_contract, pipeline_slug=pipeline_slug)
        success2, message2 = compiler2.compile(
            oml_path=str(pipeline_file),
            profile="dev",
        )
        assert success2, f"Second compilation failed: {message2}"
        hash2 = compiler2.manifest_hash
        short2 = compiler2.manifest_short

        # Compile third time
        time.sleep(0.1)

        compiler3 = CompilerV0(fs_contract=fs_contract, pipeline_slug=pipeline_slug)
        success3, message3 = compiler3.compile(
            oml_path=str(pipeline_file),
            profile="dev",
        )
        assert success3, f"Third compilation failed: {message3}"
        hash3 = compiler3.manifest_hash
        short3 = compiler3.manifest_short

        # Assert all hashes are identical
        assert hash1 == hash2, f"Hash changed between compilations: {hash1} != {hash2}"
        assert hash2 == hash3, f"Hash changed on third compilation: {hash2} != {hash3}"
        assert short1 == short2 == short3, f"Short hash changed: {short1}, {short2}, {short3}"

        # Verify only one build directory exists
        manifest_dirs = list(build_path.iterdir())
        # Filter out symlinks like LATEST
        manifest_dirs = [d for d in manifest_dirs if not d.is_symlink()]
        assert len(manifest_dirs) == 1, f"Expected 1 build dir, found {len(manifest_dirs)}: {manifest_dirs}"

        # Verify manifest fingerprints are identical
        manifest_path = manifest_dirs[0] / "manifest.yaml"
        with open(manifest_path) as f:
            manifest = yaml.safe_load(f)

        fingerprints = manifest.get("pipeline", {}).get("fingerprints", {})
        assert "manifest_fp" in fingerprints, "manifest_fp missing from fingerprints"

        # Clean up
        shutil.rmtree(build_path)

    finally:
        os.chdir(old_cwd)


