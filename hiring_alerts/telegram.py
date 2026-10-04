import html
import time
from collections.abc import Callable
from typing import Any

import requests

from .logging_setup import event
from .models import AlertError, Post


def format_post(post: Post) -> str:
    # Bound the label/link too, keeping the decoded text below Telegram's 4096 limit.
    label = (post.author or post.title or "LinkedIn post")[:300]
    if len(post.url) > 1800:
        raise AlertError("Post URL is too long for a Telegram alert")
    return ("🚨 <b>Hiring alert</b>\n" + html.escape(label) + "\n"
            + html.escape(post.text[:300]) + "\n" + html.escape(post.url))


class Telegram:
    def __init__(self, token: str, chat_id: str, session: requests.Session,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if not token or not chat_id:
            raise AlertError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
        self._url = f"https://api.telegram.org/bot{token}/sendMessage"
        self._chat_id = chat_id
        self._session, self._sleep, self._clock = session, sleep, clock
        self._next_send = 0.0

    def send(self, text: str) -> None:
        for attempt in range(3):
            self._sleep(max(0.0, self._next_send - self._clock()))
            self._next_send = self._clock() + 1.05
            retry_after = float(2 ** attempt)
            try:
                response = self._session.post(self._url, json={
                    "chat_id": self._chat_id, "text": text, "parse_mode": "HTML",
                    "link_preview_options": {"is_disabled": True},
                }, timeout=(10, 30))
                try:
                    body: Any = response.json()
                except ValueError:
                    body = {}
                if not isinstance(body, dict):
                    body = {}
                code = body.get("error_code", response.status_code)
                if response.status_code == 200 and body.get("ok") is True and isinstance(body.get("result"), dict) and "message_id" in body["result"]:
                    return
                if response.status_code == 429 or code == 429:
                    parameters = body.get("parameters", {})
                    try:
                        retry_after = max(1.0, float(parameters.get("retry_after", response.headers.get("Retry-After", 1))))
                    except (ValueError, TypeError, AttributeError):
                        retry_after = 1.0
                elif response.status_code < 500 and response.status_code != 408:
                    raise AlertError("Telegram rejected sendMessage; check chat ID, bot access, and message format")
            except requests.RequestException:
                pass  # Never expose exception strings: requests includes the bot token in URLs.
            if attempt < 2:
                event("telegram_retry", attempt=attempt + 1, delay_seconds=retry_after)
                self._sleep(retry_after)
        raise AlertError("Telegram send failed after 3 attempts; post remains pending")
