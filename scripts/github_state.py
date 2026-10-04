"""Keep SQLite in alerts-state without staging code or secrets. Run at repo root."""
import argparse
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile

BRANCH = "alerts-state"
REF = "refs/remotes/origin/" + BRANCH
DATABASE = Path("state/alerts.sqlite3")


def git(*args: str, data: bytes | None = None, env: dict[str, str] | None = None) -> bytes:
    result = subprocess.run(["git", *args], input=data, capture_output=True, env=env)
    if result.returncode:
        raise RuntimeError(f"Git {args[0]} failed (exit {result.returncode}); check permissions/connectivity")
    return result.stdout


def remote_parent() -> str | None:
    # An authentication/network error must not be mistaken for missing state.
    result = git("ls-remote", "--heads", "origin", "refs/heads/" + BRANCH).strip()
    if not result:
        return None
    git("fetch", "--no-tags", "origin", f"refs/heads/{BRANCH}:{REF}")
    return git("rev-parse", REF).decode().strip()


def validate_database(path: Path) -> None:
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        if db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise RuntimeError("SQLite integrity check failed; preserve existing state")
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"seen", "pending", "initialized"}.issubset(tables):
            raise RuntimeError("State database is missing required tables")
    finally:
        db.close()


def restore() -> None:
    parent = remote_parent()
    if parent is None:
        print("No state branch yet; first successful fetch will initialize sources.")
        return
    payload = git("show", f"{parent}:alerts.sqlite3")
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    DATABASE.write_bytes(payload)
    validate_database(DATABASE)
    print("Restored SQLite from alerts-state branch.")


def save() -> None:
    validate_database(DATABASE)
    parent = remote_parent()
    blob = git("hash-object", "-w", "--stdin", data=DATABASE.read_bytes()).decode().strip()
    if parent and git("rev-parse", f"{parent}:alerts.sqlite3").decode().strip() == blob:
        print("State unchanged; no commit needed.")
        return
    with tempfile.TemporaryDirectory(prefix="alerts-index-") as temp:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(temp) / "index"),
                   GIT_AUTHOR_NAME="Hiring alerts", GIT_COMMITTER_NAME="Hiring alerts",
                   GIT_AUTHOR_EMAIL="actions@users.noreply.github.com",
                   GIT_COMMITTER_EMAIL="actions@users.noreply.github.com")
        git("read-tree", "--empty", env=env)
        git("update-index", "--add", "--cacheinfo", f"100644,{blob},alerts.sqlite3", env=env)
        tree = git("write-tree", env=env).decode().strip()
        args = ["commit-tree", tree]
        if parent:
            args.extend(["-p", parent])
        commit = git(*args, data=b"Persist hiring alert state\n", env=env).decode().strip()
        # Never force push over another run's state.
        git("push", "origin", f"{commit}:refs/heads/{BRANCH}")
    print("Saved SQLite to alerts-state branch.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["restore", "save"])
    args = parser.parse_args()
    try:
        (restore if args.action == "restore" else save)()
        return 0
    except (RuntimeError, OSError, sqlite3.Error) as exc:
        print(str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
