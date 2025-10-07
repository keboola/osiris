"""Tests for ProxyWorker dependency installation logic."""

from pathlib import Path

from osiris.remote.proxy_worker import ProxyWorker


class DummyResult:
    def __init__(self, returncode=0, stdout="Successfully installed pkg", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_install_requirements_prefers_uploaded_requirements(tmp_path, monkeypatch):
    worker = ProxyWorker()
    worker.session_id = "test-session"
    worker.session_dir = tmp_path
    worker.artifacts_root = tmp_path / "artifacts"
    worker.artifacts_root.mkdir(parents=True, exist_ok=True)
    worker.send_event = lambda *args, **kwargs: None  # Silence events during test

    requirements_file = tmp_path / "requirements_e2b.txt"
    requirements_file.write_text("example-pkg==1.0\n")

    calls = []

    def fake_run(cmd, **kwargs):  # noqa: D401 - simple stub
        calls.append(cmd)
        return DummyResult()

    monkeypatch.setattr("subprocess.run", fake_run)

    result = worker._install_requirements(set())

    assert any("requirements_e2b.txt" in str(part) for cmd in calls for part in cmd)
    log_path = Path(result["log_path"])
    assert log_path.exists()
    assert "pip_install.log" in str(log_path)
