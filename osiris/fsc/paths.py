"""Path resolution over the filesystem contract."""

from pathlib import Path
import re

from osiris.fsc.config import FilesystemConfig

_SLUG_STRIP = re.compile(r"[^a-z0-9_]+")
_SEGMENT_STRIP = re.compile(r"[^A-Za-z0-9_]+")


def slugify(value: str) -> str:
    """Lowercase, runs of non-alphanumerics collapsed to a single hyphen, edges stripped.

    For human-authored names -- a plan called "Cinema Listings — Well Rated!" should
    reach the filesystem as one predictable thing however it was typed.

    Underscores survive verbatim because they are structural separators in generated
    identifiers; mangling them would stop a run's directory name from matching the run
    id recorded in the run index. Every other non-alphanumeric -- notably `.`, `/` and
    `\\` -- is collapsed away, which is what makes path traversal structurally
    impossible rather than merely checked for.
    """
    return _SLUG_STRIP.sub("-", value.lower()).strip("-")


def sanitize_segment(value: str) -> str:
    """Same traversal defense as `slugify`, but case-preserving.

    For identifiers Osiris generated itself, where the exact string is the thing you
    look up by. Run ids are `run_<UTC compact ISO>_<hex>`: lowercasing them made the
    run index unnavigable, because the id it recorded (`…T192357Z…`) was not the
    directory that existed (`…t192357z…`). That only shows up on a case-sensitive
    filesystem -- which is to say, in CI and in production, but not on a developer's
    Mac -- and no test caught it because every test built both sides of the comparison
    through the same lowercasing helper. Two identically broken paths agree.
    """
    return _SEGMENT_STRIP.sub("-", value).strip("-")


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
        # The plan name is human-authored and gets normalized; the run id is ours
        # and must survive verbatim, because the run index records it as the way
        # to find this directory.
        return self.base / self._config.run_logs_dir / slugify(plan_name) / sanitize_segment(run_id)

    def session_dir(self, session_id: str) -> Path:
        return self.base / self._config.sessions_dir / sanitize_segment(session_id)

    def run_index_path(self) -> Path:
        return self.base / self._config.index_dir / "runs.jsonl"
