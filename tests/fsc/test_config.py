"""Filesystem config is loaded from osiris.yaml and never guesses."""

import pytest
import yaml

from osiris.fsc.config import FilesystemConfig


def test_load_reads_base_path_from_osiris_yaml(tmp_path):
    (tmp_path / "osiris.yaml").write_text(
        yaml.safe_dump({"filesystem": {"base_path": str(tmp_path), "build_dir": "artifacts"}})
    )
    cfg = FilesystemConfig.load(tmp_path)
    assert cfg.base_path == tmp_path
    assert cfg.build_dir == "artifacts"


def test_load_applies_documented_defaults(tmp_path):
    (tmp_path / "osiris.yaml").write_text(yaml.safe_dump({"filesystem": {"base_path": str(tmp_path)}}))
    cfg = FilesystemConfig.load(tmp_path)
    assert cfg.build_dir == "build"
    assert cfg.run_logs_dir == "run_logs"


def test_load_fails_loudly_when_config_missing(tmp_path):
    with pytest.raises(FileNotFoundError, match="osiris.yaml"):
        FilesystemConfig.load(tmp_path)


def test_load_fails_loudly_when_base_path_missing(tmp_path):
    (tmp_path / "osiris.yaml").write_text(yaml.safe_dump({"filesystem": {}}))
    with pytest.raises(ValueError, match="base_path"):
        FilesystemConfig.load(tmp_path)
