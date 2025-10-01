import hashlib

from osiris.remote.proxy_worker import ProxyWorker


def test_emit_driver_file_verification(tmp_path, monkeypatch):
    worker = ProxyWorker()

    driver_path = tmp_path / "supabase_writer_driver.py"
    driver_path.write_text("print('hello world')\n", encoding="utf-8")

    captured = {}

    def fake_send_event(event_name: str, **kwargs):
        captured["name"] = event_name
        captured["payload"] = kwargs

    monkeypatch.setattr(worker, "send_event", fake_send_event)

    worker._emit_driver_file_verification(driver_name="supabase.writer", sandbox_path=driver_path)

    assert captured["name"] == "driver_file_verified"
    payload = captured["payload"]
    assert payload["driver"] == "supabase.writer"
    assert payload["path"] == str(driver_path)

    expected_hash = hashlib.sha256(driver_path.read_bytes()).hexdigest()
    assert payload["sha256"] == expected_hash
    assert payload["size_bytes"] == driver_path.stat().st_size


def test_emit_driver_file_verification_missing_file(monkeypatch, tmp_path):
    worker = ProxyWorker()

    missing_path = tmp_path / "missing_driver.py"

    captured = {}

    def fake_send_event(event_name: str, **kwargs):
        captured["name"] = event_name
        captured["payload"] = kwargs

    monkeypatch.setattr(worker, "send_event", fake_send_event)

    worker._emit_driver_file_verification(driver_name="supabase.writer", sandbox_path=missing_path)

    assert captured["name"] == "driver_file_verified"
    payload = captured["payload"]
    assert payload["driver"] == "supabase.writer"
    assert payload["path"] == str(missing_path)
    assert payload["error"] == "not_found"
