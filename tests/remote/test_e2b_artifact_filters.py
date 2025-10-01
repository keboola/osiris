from types import SimpleNamespace

import pytest

from osiris.remote.e2b_transparent_proxy import E2BTransparentProxy


class FakeCommands:
    def __init__(self, files):
        self.files = files

    async def run(self, cmd: str):
        if "test -d" in cmd:
            return SimpleNamespace(stdout="exists")
        if "find" in cmd:
            listing = "\n".join(sorted(self.files.keys()))
            return SimpleNamespace(stdout=listing)
        if "stat -c %s" in cmd:
            rel = cmd.split("artifacts/")[1]
            size = self.files.get(rel, {}).get("size", 0)
            return SimpleNamespace(stdout=str(size))
        return SimpleNamespace(stdout="")


class FakeFiles:
    def __init__(self, files):
        self.files = files

    async def read(self, path: str):
        rel = path.split("artifacts/")[1]
        return self.files[rel]["content"]


def make_proxy(tmp_path, files, monkeypatch, *, download_data="0", max_mb="5"):
    proxy = E2BTransparentProxy(config={"api_key": "dummy"})
    proxy.session_id = "session"
    proxy.sandbox = SimpleNamespace(commands=FakeCommands(files), files=FakeFiles(files))

    monkeypatch.setenv("E2B_DOWNLOAD_DATA_ARTIFACTS", download_data)
    monkeypatch.setenv("E2B_ARTIFACT_MAX_MB", max_mb)

    context = SimpleNamespace(session_id="session", logs_dir=tmp_path)
    return proxy, context


@pytest.mark.asyncio
async def test_artifact_filter_skips_large_data(tmp_path, monkeypatch):
    files = {
        "data/output.pkl": {
            "content": b"x" * (10 * 1024 * 1024),
            "size": 10 * 1024 * 1024,
        },
        "_system/pip.log": {
            "content": b"log",
            "size": 3,
        },
    }

    proxy, context = make_proxy(tmp_path, files, monkeypatch)

    await proxy._download_artifacts(context)

    downloaded = list((tmp_path / "artifacts").rglob("*"))
    assert any(path.name == "pip.log" for path in downloaded)
    assert not any(path.name == "output.pkl" for path in downloaded)


@pytest.mark.asyncio
async def test_artifact_filter_allows_data_when_opt_in(tmp_path, monkeypatch):
    files = {
        "data/output.pkl": {
            "content": b"data",
            "size": 4,
        },
    }

    proxy, context = make_proxy(tmp_path, files, monkeypatch, download_data="1")

    await proxy._download_artifacts(context)

    downloaded = list((tmp_path / "artifacts").rglob("*"))
    assert any(path.name == "output.pkl" for path in downloaded)
