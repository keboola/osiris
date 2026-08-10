"""Run ids are sortable, unique, and timestamped in UTC."""

from datetime import UTC, datetime

from osiris.evidence.run_ids import new_run_id


def test_run_id_shape():
    rid = new_run_id(datetime(2026, 8, 10, 14, 5, 9, tzinfo=UTC))
    assert rid.startswith("run_20260810T140509Z_")
    assert len(rid) == len("run_20260810T140509Z_") + 6


def test_run_ids_are_unique():
    now = datetime(2026, 8, 10, 14, 5, 9, tzinfo=UTC)
    assert len({new_run_id(now) for _ in range(200)}) > 190


def test_run_ids_sort_chronologically():
    early = new_run_id(datetime(2026, 8, 10, 1, 0, 0, tzinfo=UTC))
    late = new_run_id(datetime(2026, 8, 10, 2, 0, 0, tzinfo=UTC))
    assert early < late
