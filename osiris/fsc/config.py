"""Filesystem contract configuration. Every path is config-driven."""

from pathlib import Path

from pydantic import BaseModel
import yaml

CONFIG_FILENAME = "osiris.yaml"


class FilesystemConfig(BaseModel):
    """Where Osiris puts things. Loaded from osiris.yaml; no invented defaults for base_path."""

    base_path: Path
    build_dir: str = "build"
    run_logs_dir: str = "run_logs"
    sessions_dir: str = ".osiris/sessions"
    index_dir: str = ".osiris/index"

    @classmethod
    def load(cls, start: Path | None = None) -> "FilesystemConfig":
        """Read osiris.yaml from `start` (default: cwd). Fails loudly when absent or incomplete."""
        root = Path(start) if start is not None else Path.cwd()
        config_path = root / CONFIG_FILENAME
        if not config_path.exists():
            raise FileNotFoundError(f"{CONFIG_FILENAME} not found in {root}. Run 'osiris init' first.")

        raw = yaml.safe_load(config_path.read_text()) or {}
        fs = raw.get("filesystem") or {}
        if not fs.get("base_path"):
            raise ValueError(f"{config_path}: filesystem.base_path is required and must not be empty.")

        return cls(
            base_path=Path(fs["base_path"]),
            build_dir=fs.get("build_dir", "build"),
            run_logs_dir=fs.get("run_logs_dir", "run_logs"),
            sessions_dir=fs.get("sessions_dir", ".osiris/sessions"),
            index_dir=fs.get("index_dir", ".osiris/index"),
        )


class PathsConfigError(ValueError):
    """Raised when a resolved path would escape base_path."""
