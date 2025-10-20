from hashlib import sha256
import json
from pathlib import Path
import time
from types import SimpleNamespace

from osiris.remote.e2b_transparent_proxy import E2BTransparentProxy


def test_forward_event_driver_file_verification(tmp_path):
    proxy = E2BTransparentProxy(config={"api_key": "dummy"})
    proxy.session_id = "session-123"
    proxy.context = SimpleNamespace(logs_dir=tmp_path)

    repo_root = Path(__file__).resolve().parents[2]
    driver_path = repo_root / "osiris" / "drivers" / "supabase_writer_driver.py"
    driver_bytes = driver_path.read_bytes()

    event = {
        "name": "driver_file_verified",
        "data": {
            "driver": "supabase.writer",
            "path": "/home/user/osiris/drivers/supabase_writer_driver.py",
            "sha256": sha256(driver_bytes).hexdigest(),
            "size_bytes": len(driver_bytes),
        },
        "timestamp": time.time(),
    }

    proxy._forward_event_to_host(event)

    events_file = tmp_path / "events.jsonl"
    written = events_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(written) == 1

    payload = json.loads(written[0])
    assert payload["event"] == "driver_file_verified"
    assert payload["driver"] == "supabase.writer"
    assert payload["sha256_match"] is True
    assert payload["match"] is True
    assert payload["host_sha256"] == payload["sha256"]
    assert payload["host_size_bytes"] == payload["size_bytes"]
