"""Path resolution over the filesystem contract."""

from pathlib import Path
import re

from osiris.fsc.config import FilesystemConfig

_SLUG_STRIP = re.compile(r"[^a-z0-9_]+")


def slugify(value: str) -> str:
    """Lowercase, runs of non-alphanumerics collapsed to a single hyphen, edges stripped.

    Underscores survive verbatim because they are structural separators in generated
    identifiers (`run_<timestamp>_<hex>`); mangling them would stop a run's directory
    name from matching the run id recorded in the run index. Every other non-alphanumeric
    -- notably `.`, `/` and `\\` -- is collapsed away, which is what makes path traversal
    structurally impossible rather than merely checked for.
    """
    return _SLUG_STRIP.sub("-", value.lower()).strip("-")


class Paths:
    """Resolves every Osiris path from a FilesystemConfig."""

    def __init__(self, config: FilesystemConfig) -> None:
        self._config = config

    @property
    def base(self) -> Path:
        return self._config.base_path

    def build_dir(self, plan_name: str, manifest_hash: str) -> Path:
        return self.base / self._config.build_dir / slugify(plan_name) / slugify(manifest_hash)

    def run_log_dir(self, plan_name: str, run_id: str) -> Path:
        return self.base / self._config.run_logs_dir / slugify(plan_name) / slugify(run_id)

    def session_dir(self, session_id: str) -> Path:
        return self.base / self._config.sessions_dir / slugify(session_id)

    def run_index_path(self) -> Path:
        return self.base / self._config.index_dir / "runs.jsonl"
