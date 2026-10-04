from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from .models import AlertError


@dataclass(frozen=True)
class Config:
    google_enabled: bool
    feed_urls: list[str]
    apify_enabled: bool
    apify_timeout: int
    apify_poll: int
    fields: dict[str, str]
    include: list[str]
    exclude: list[str]
    max_messages: int
    state_path: Path


def _strings(value: Any, key: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
        raise AlertError(f"Config {key} must be a list of nonempty strings")
    return [v.strip() for v in value]


def _integer(value: Any, key: str, minimum: int = 1) -> int:
    if type(value) is not int or value < minimum:
        raise AlertError(f"Config {key} must be an integer >= {minimum}")
    return value


def load_config(path: Path) -> Config:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        raise AlertError("Cannot read config: check file path and YAML syntax") from None
    if not isinstance(data, dict):
        raise AlertError("Config must be a YAML mapping")
    google, apify = data.get("google_alerts", {}), data.get("apify", {})
    if not isinstance(google, dict) or not isinstance(apify, dict):
        raise AlertError("Source settings must be mappings")
    for name, source in (("google_alerts", google), ("apify", apify)):
        if type(source.get("enabled", False)) is not bool:
            raise AlertError(f"Config {name}.enabled must be true or false")
    feeds = _strings(google.get("feed_urls", []), "feed_urls")
    try:
        if any(urlsplit(url).scheme not in {"https", "http"} or not urlsplit(url).hostname for url in feeds):
            raise ValueError
    except ValueError:
        raise AlertError("Feed URLs must be absolute HTTP(S) URLs") from None
    if google.get("enabled") and not feeds:
        raise AlertError("Google Alerts is enabled but feed_urls is empty")
    if not (google.get("enabled") or apify.get("enabled")):
        raise AlertError("Enable at least one source in config.yaml")
    fields = {"url_field": "url", "author_field": "author", "text_field": "text", "date_field": "publishedAt"}
    custom = apify.get("fields", {})
    if not isinstance(custom, dict) or set(custom) - set(fields):
        raise AlertError("Invalid Apify fields mapping keys")
    fields.update(custom)
    if any(not isinstance(v, str) or not v.strip() for v in fields.values()):
        raise AlertError("Apify field paths must be nonempty strings")
    state = data.get("state_path", "state/alerts.sqlite3")
    if not isinstance(state, str) or not state.strip():
        raise AlertError("state_path must be a nonempty path")
    return Config(google.get("enabled", False), list(dict.fromkeys(feeds)), apify.get("enabled", False),
                  _integer(apify.get("timeout_seconds", 300), "timeout_seconds"),
                  _integer(apify.get("poll_seconds", 5), "poll_seconds"), fields,
                  _strings(data.get("include_keywords", []), "include_keywords"),
                  _strings(data.get("exclude_keywords", []), "exclude_keywords"),
                  _integer(data.get("max_messages_per_run", 15), "max_messages_per_run", 2),
                  path.resolve().parent / state)
