"""Paths are derived from config and are slug-stable."""

from pathlib import Path

from osiris.fsc.config import FilesystemConfig
from osiris.fsc.paths import Paths, sanitize_segment, slugify


def _cfg(tmp_path: Path) -> FilesystemConfig:
    return FilesystemConfig(base_path=tmp_path)


def test_slugify_lowercases_and_replaces_separators():
    assert slugify("Cinema Listings — Well Rated!") == "cinema-listings-well-rated"


def test_slugify_collapses_repeats_and_strips_edges():
    assert slugify("--a  b--") == "a-b"


def test_build_dir_is_slug_and_hash(tmp_path):
    p = Paths(_cfg(tmp_path))
    assert p.build_dir("Cinema Listings", "a71f3c9") == tmp_path / "build" / "cinema-listings" / "a71f3c9"


def test_run_log_dir_is_slug_and_run_id(tmp_path):
    p = Paths(_cfg(tmp_path))
    assert p.run_log_dir("Cinema Listings", "run_01") == tmp_path / "run_logs" / "cinema-listings" / "run_01"


def test_session_and_index_live_under_dot_osiris(tmp_path):
    p = Paths(_cfg(tmp_path))
    assert p.session_dir("sess_1") == tmp_path / ".osiris" / "sessions" / "sess_1"
    assert p.run_index_path() == tmp_path / ".osiris" / "index" / "runs.jsonl"


HOSTILE_NAMES = (
    "../escape",
    "..",
    "/etc/passwd",
    "..\\..\\windows",
    "a/../../b",
    "....//....//x",
)


def test_slugify_dissolves_every_traversal_character():
    """Traversal is impossible because the characters that express it cannot survive a slug."""
    for hostile in HOSTILE_NAMES:
        slug = slugify(hostile)
        assert "." not in slug, f"{hostile!r} -> {slug!r} kept a dot"
        assert "/" not in slug, f"{hostile!r} -> {slug!r} kept a forward slash"
        assert "\\" not in slug, f"{hostile!r} -> {slug!r} kept a backslash"


def test_no_path_escapes_base_path(tmp_path):
    """Every resolved path stays strictly inside base_path, for every hostile component."""
    p = Paths(_cfg(tmp_path))
    base = tmp_path.resolve()
    candidates = []
    for hostile in HOSTILE_NAMES:
        candidates += [
            p.build_dir(hostile, "h"),
            p.build_dir("plan", hostile),
            p.run_log_dir(hostile, "r"),
            p.run_log_dir("plan", hostile),
            p.session_dir(hostile),
        ]

    for candidate in candidates:
        # No traversal component survives even lexically, so `..` cannot be
        # re-interpreted by a later consumer that joins without resolving.
        assert ".." not in candidate.parts, f"{candidate} retains a traversal component"
        # Containment holds after resolution -- this is the assertion that would
        # actually catch an escape, since Path.parents alone is purely lexical.
        resolved = candidate.resolve()
        assert resolved.is_relative_to(base), f"{candidate} resolves outside base to {resolved}"
        # And it lands strictly below base, never on base itself.
        assert resolved != base, f"{candidate} collapsed onto base_path itself"


# --- Generated ids must survive verbatim ------------------------------------
#
# Found by hands-on testing, not by the suite: the run index recorded
# `run_20260810T192357Z_493c91` while the directory was `…t192357z…`. On macOS
# the mismatch is invisible (APFS is case-insensitive); on Linux, which is CI
# and production, following the ledger to its evidence fails outright. No test
# caught it because every test built both sides through the same lowercasing
# helper — two identically broken paths agree.


def test_sanitize_segment_preserves_case():
    assert sanitize_segment("run_20260810T192357Z_493c91") == "run_20260810T192357Z_493c91"


def test_sanitize_segment_still_dissolves_traversal():
    for hostile in ("../escape", "..", "/etc/passwd", "..\\..\\windows", "a/../../b", "....//x"):
        out = sanitize_segment(hostile)
        assert ".." not in out
        assert "/" not in out and "\\" not in out


def test_run_log_dir_keeps_the_run_id_exactly(tmp_path):
    """The whole point: what the ledger records is what `ls` finds."""
    p = Paths(_cfg(tmp_path))
    run_id = "run_20260810T192357Z_493c91"
    assert p.run_log_dir("Cinema Digest", run_id).name == run_id


def test_run_log_dir_still_normalizes_the_plan_name(tmp_path):
    p = Paths(_cfg(tmp_path))
    assert p.run_log_dir("Cinema Digest!", "run_1").parent.name == "cinema-digest"


def test_session_dir_keeps_the_session_id_exactly(tmp_path):
    p = Paths(_cfg(tmp_path))
    assert p.session_dir("sess_20260810T192357Z_ab12").name == "sess_20260810T192357Z_ab12"


def test_a_run_id_from_the_generator_round_trips(tmp_path):
    """Generate a real id, build its path, and read the name back."""
    from osiris.evidence.run_ids import new_run_id

    run_id = new_run_id()
    assert Paths(_cfg(tmp_path)).run_log_dir("demo", run_id).name == run_id
