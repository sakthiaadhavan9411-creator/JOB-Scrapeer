import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from collections.abc import Iterator, Sequence

from .models import AlertError, Post


@contextmanager
def run_lock(path: Path) -> Iterator[None]:
    """An OS lock released on crash; serialize runs sharing one state file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(path.suffix + ".lock").open("a+b") as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise AlertError("Another process is using this state file") from None
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class State:
    def __init__(self, path: Path, dry_run: bool = False) -> None:
        if dry_run:
            self.db = sqlite3.connect(":memory:")
            if path.exists():
                source = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
                try:
                    source.backup(self.db)
                finally:
                    source.close()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(path)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS seen (url TEXT PRIMARY KEY, reason TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS initialized (source TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS pending (url TEXT PRIMARY KEY, payload TEXT NOT NULL);
        """)

    def close(self) -> None:
        self.db.close()

    def initialized(self, source: str) -> bool:
        return self.db.execute("SELECT 1 FROM initialized WHERE source=?", (source,)).fetchone() is not None

    def seen(self, url: str) -> bool:
        return self.db.execute("SELECT 1 FROM seen WHERE url=?", (url,)).fetchone() is not None

    def stage(self, source: str, posts: Sequence[Post], baseline: set[str]) -> None:
        with self.db:
            for post in posts:
                if self.seen(post.url):
                    continue
                if post.url in baseline:
                    # A new source must not discard an already queued post from another source.
                    if not self.db.execute("SELECT 1 FROM pending WHERE url=?", (post.url,)).fetchone():
                        self.db.execute("INSERT OR IGNORE INTO seen VALUES (?, 'baseline')", (post.url,))
                else:
                    self.db.execute("INSERT OR IGNORE INTO pending VALUES (?, ?)",
                                    (post.url, json.dumps(asdict(post))))
            self.db.execute("INSERT OR IGNORE INTO initialized VALUES (?)", (source,))

    def pending(self) -> list[Post]:
        return [Post(**json.loads(row[0])) for row in self.db.execute("SELECT payload FROM pending ORDER BY rowid")]

    def acknowledge(self, url: str) -> None:
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO seen VALUES (?, 'sent')", (url,))
            self.db.execute("DELETE FROM pending WHERE url=?", (url,))
