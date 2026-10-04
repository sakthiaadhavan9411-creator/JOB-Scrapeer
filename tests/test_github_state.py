import importlib.util
from pathlib import Path
import shutil
import subprocess

import pytest

from hiring_alerts.dedupe import State


def test_durable_state_roundtrip(tmp_path, monkeypatch):
    if not shutil.which("git"):
        pytest.skip("git is not installed")
    spec = importlib.util.spec_from_file_location("github_state", Path(__file__).parents[1] / "scripts/github_state.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    remote, repo = tmp_path / "remote.git", tmp_path / "repo"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    monkeypatch.chdir(repo)
    module.git("remote", "add", "origin", str(remote))
    module.restore()
    assert not module.DATABASE.exists()
    state = State(module.DATABASE)
    state.stage("feed", [], set())
    state.acknowledge("https://linkedin.com/posts/example")
    state.close()
    module.save()
    first = module.remote_parent()
    module.save()
    assert module.remote_parent() == first
    assert module.git("ls-tree", "--name-only", first).decode().strip() == "alerts.sqlite3"
    module.DATABASE.unlink()
    module.restore()
    state = State(module.DATABASE)
    assert state.initialized("feed")
    assert state.seen("https://linkedin.com/posts/example")
    state.acknowledge("https://linkedin.com/posts/second")
    state.close()
    module.save()
    assert module.remote_parent() != first
    assert module.git("rev-parse", module.remote_parent() + "^").decode().strip() == first
