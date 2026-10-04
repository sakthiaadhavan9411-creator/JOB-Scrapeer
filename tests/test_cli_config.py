import json
from unittest.mock import Mock

import pytest
import yaml

from hiring_alerts.cli import main
from hiring_alerts.config import load_config
from hiring_alerts.models import AlertError, Post


def write_config(tmp_path, **changes):
    data = {"google_alerts": {"enabled": True, "feed_urls": ["https://example.org/feed"]}}
    data.update(changes)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_defaults_and_relative_state(tmp_path):
    config = load_config(write_config(tmp_path))
    assert config.max_messages == 15
    assert config.state_path == tmp_path / "state" / "alerts.sqlite3"
    assert config.fields["date_field"] == "publishedAt"


@pytest.mark.parametrize("changes", [{"max_messages_per_run": 0}, {"include_keywords": "hiring"},
                                     {"google_alerts": {"enabled": "false"}},
                                     {"apify": {"fields": {"url_field": None}}}])
def test_config_errors(tmp_path, changes):
    with pytest.raises(AlertError):
        load_config(write_config(tmp_path, **changes))


def test_cli_dry_run_end_to_end(tmp_path, monkeypatch, capsys):
    path = write_config(tmp_path)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setattr("sys.argv", ["hiring_alerts", "run", "--config", str(path), "--dry-run", "--send-backlog", "1"])
    post = Post("https://www.linkedin.com/posts/abc/?utm_source=google", "<b>Hiring</b>", text="Python &amp; SQL")
    monkeypatch.setattr("hiring_alerts.pipeline.fetch_feed", lambda *_: [post])
    assert main() == 0
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    preview = next(row["message"] for row in rows if row["event"] == "would_send")
    assert "https://linkedin.com/posts/abc" in preview and "utm_source" not in preview
    assert "Python &amp; SQL" in preview
    assert not (tmp_path / "state").exists()


def test_logs_never_print_raw_source_exception(tmp_path, monkeypatch, capsys):
    path = write_config(tmp_path)
    monkeypatch.setattr("sys.argv", ["hiring_alerts", "run", "--config", str(path), "--dry-run"])
    monkeypatch.setattr("hiring_alerts.pipeline.fetch_feed", Mock(side_effect=RuntimeError("SECRET_TOKEN")))
    assert main() == 1
    output = capsys.readouterr().out
    assert "SECRET_TOKEN" not in output and "source_failed" in output
