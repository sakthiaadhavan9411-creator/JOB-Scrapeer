import hashlib
import logging
import os
from collections.abc import Callable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

from .config import Config
from .dedupe import State
from .filters import matches
from .logging_setup import event
from .models import AlertError, Post
from .normalize import normalize_post
from .sources.apify import fetch_task
from .sources.google_alerts import fetch_feed
from .telegram import Telegram, format_post

Source = tuple[str, Callable[[], list[Post]]]


def sources(config: Config, session: requests.Session) -> list[Source]:
    result: list[Source] = []
    if config.google_enabled:
        for url in config.feed_urls:
            key = "rss:" + hashlib.sha256(url.encode()).hexdigest()[:16]
            result.append((key, lambda url=url: fetch_feed(url, session)))
    if config.apify_enabled:
        task = os.getenv("APIFY_TASK_ID", "")
        key = "apify:" + hashlib.sha256(task.encode()).hexdigest()[:16]
        result.append((key, lambda: fetch_task(os.getenv("APIFY_TOKEN", ""), task, config.fields,
                                               config.apify_timeout, config.apify_poll, session)))
    return result


def _published(post: Post) -> float:
    for parse in (lambda s: datetime.fromisoformat(s.replace("Z", "+00:00")), parsedate_to_datetime):
        try:
            value = parse(post.published)
            return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).timestamp()
        except (ValueError, TypeError, OverflowError):
            continue
    return 0.0


def process(config: Config, state: State, source_list: list[Source], sender: Telegram | None,
            dry_run: bool = False, send_backlog: int = 0) -> bool:
    """Return false on any source/delivery failure, after processing healthy sources."""
    healthy: list[tuple[str, list[Post], bool]] = []
    success = True
    for key, fetch in source_list:
        try:
            posts = [normalized for p in fetch() if (normalized := normalize_post(p)) is not None]
            healthy.append((key, posts, not state.initialized(key)))
            event("source_fetched", source=key, linkedin_posts=len(posts))
        except Exception as exc:
            success = False
            # Only our curated operational errors are safe to display.
            event("source_failed", logging.ERROR, source=key,
                  error=str(exc) if isinstance(exc, AlertError) else type(exc).__name__)

    first_posts = {p.url: p for _, posts, first in healthy if first for p in posts}
    eligible = [p for p in first_posts.values() if matches(p, config.include, config.exclude) and not state.seen(p.url)]
    selected = {p.url for p in sorted(eligible, key=_published, reverse=True)[:send_backlog]}
    # Existing initialized sources take precedence over a newly added source's baseline.
    regular = {p.url for _, posts, first in healthy if not first for p in posts
               if matches(p, config.include, config.exclude)}
    baseline = set(first_posts) - selected - regular
    for key, posts, first in healthy:
        staged = posts if first else [p for p in posts if matches(p, config.include, config.exclude)]
        state.stage(key, staged, baseline if first else set())
        if first:
            event("source_initialized", source=key, baselined=sum(p.url in baseline for p in posts), dry_run=dry_run)

    # Reapply current filters, including to durable pending records.
    pending = [p for p in state.pending() if matches(p, config.include, config.exclude)]
    # The cap includes the summary: reserve one slot only when needed.
    count = config.max_messages if len(pending) <= config.max_messages else config.max_messages - 1
    batch = pending[:count]
    for post in batch:
        try:
            message = format_post(post)
            if dry_run:
                event("would_send", message=message)
            else:
                if sender is None:
                    raise AlertError("Telegram sender is not configured")
                sender.send(message)
                state.acknowledge(post.url)
                event("post_sent", source=post.source)
        except AlertError as exc:
            event("delivery_failed", logging.ERROR, error=str(exc))
            return False  # Avoid hammering a broken chat; all remaining posts stay pending.
    remaining = len(pending) - len(batch)
    if remaining:
        summary = f"+{remaining} more hiring alerts pending; queued for later runs."
        try:
            if dry_run:
                event("would_send", message=summary)
            elif sender is not None:
                sender.send(summary)
        except AlertError as exc:
            event("summary_failed", logging.ERROR, error=str(exc))
            return False
    event("run_complete", sent=0 if dry_run else len(batch), pending=remaining, dry_run=dry_run)
    return success
