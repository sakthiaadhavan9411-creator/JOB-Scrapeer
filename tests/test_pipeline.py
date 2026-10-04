from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest

from hiring_alerts.config import Config
from hiring_alerts.dedupe import State, run_lock
from hiring_alerts.models import AlertError, Post
from hiring_alerts.pipeline import process


@pytest.fixture
def config(tmp_path):
    return Config(True, [], False, 300, 5, {}, ["hiring"], [], 15, tmp_path / "state.sqlite3")


def post(n):
    return Post(f"https://www.linkedin.com/posts/{n}/?trk=google", title="Hiring", text="Engineers",
                published=f"2026-01-{n + 1:02d}T00:00:00Z")


def test_first_run_then_new_post_and_duplicate(config):
    state, sender = State(config.state_path), Mock()
    assert process(config, state, [("rss", lambda: [post(0)])], sender)
    sender.send.assert_not_called()
    assert state.seen("https://linkedin.com/posts/0")
    assert process(config, state, [("rss", lambda: [post(0), post(1), post(1)])], sender)
    assert sender.send.call_count == 1
    state.close()
    reopened = State(config.state_path)
    assert reopened.seen("https://linkedin.com/posts/1")
    reopened.close()


def test_backlog_is_newest_and_failures_remain_pending(config):
    state, sender = State(config.state_path), Mock()
    sender.send.side_effect = AlertError("test failure")
    assert not process(config, state, [("rss", lambda: [post(0), post(1)])], sender, send_backlog=1)
    assert not state.seen("https://linkedin.com/posts/1")
    assert state.seen("https://linkedin.com/posts/0")
    assert len(state.pending()) == 1
    sender.send.side_effect = None
    assert process(config, state, [("rss", lambda: [])], sender)
    assert state.seen("https://linkedin.com/posts/1")
    state.close()


def test_cap_includes_summary_and_queue_survives_feed_removal(config):
    config = replace(config, max_messages=3)
    state, sender = State(config.state_path), Mock()
    process(config, state, [("rss", lambda: [])], sender)
    process(config, state, [("rss", lambda: [post(i) for i in range(5)])], sender)
    assert sender.send.call_count == 3
    assert sender.send.call_args.args[0].startswith("+3 more")
    assert len(state.pending()) == 3
    state.close()
    state = State(config.state_path)
    sender.reset_mock()
    process(config, state, [("rss", lambda: [])], sender)
    assert sender.send.call_count == 3
    assert not state.pending()
    state.close()


def test_dry_run_preserves_db_and_sends_nothing(config):
    state = State(config.state_path)
    state.stage("rss", [], set())
    state.close()
    original = config.state_path.read_bytes()
    preview, sender = State(config.state_path, dry_run=True), Mock()
    process(config, preview, [("rss", lambda: [post(0)])], sender, dry_run=True)
    preview.close()
    sender.send.assert_not_called()
    assert config.state_path.read_bytes() == original


def test_first_dry_run_creates_no_file(config):
    preview = State(config.state_path, dry_run=True)
    process(config, preview, [("rss", lambda: [post(0)])], None, dry_run=True)
    preview.close()
    assert not config.state_path.exists()


def test_source_isolation_and_delayed_baseline(config):
    state, sender = State(config.state_path), Mock()
    def fail():
        raise AlertError("outage")
    assert not process(config, state, [("good", lambda: []), ("bad", fail)], sender)
    assert state.initialized("good") and not state.initialized("bad")
    process(config, state, [("good", lambda: [post(1)]), ("bad", lambda: [post(0)])], sender)
    assert sender.send.call_count == 1
    assert "posts/1" in sender.send.call_args.args[0]
    state.close()


def test_empty_success_is_initialized(config):
    state, sender = State(config.state_path), Mock()
    process(config, state, [("rss", lambda: [])], sender)
    process(config, state, [("rss", lambda: [post(0)])], sender)
    sender.send.assert_called_once()
    state.close()


def test_new_source_does_not_swallow_regular_source_post(config):
    state, sender = State(config.state_path), Mock()
    state.stage("old", [], set())
    process(config, state, [("new", lambda: [post(0)]), ("old", lambda: [post(0)])], sender)
    sender.send.assert_called_once()
    state.close()


def test_lock_excludes_second_process(config):
    with run_lock(config.state_path):
        with pytest.raises(AlertError, match="Another process"):
            with run_lock(config.state_path):
                pass
