from unittest.mock import Mock

import pytest
import requests

from hiring_alerts.models import AlertError, Post
from hiring_alerts.telegram import Telegram, format_post


def response(status=200, body=None):
    return Mock(status_code=status, headers={}, json=Mock(return_value=body if body is not None else {"ok": True, "result": {"message_id": 1}}))


def test_429_retry_after():
    session, sleep = Mock(), Mock()
    session.post.side_effect = [response(429, {"ok": False, "parameters": {"retry_after": 7}}), response()]
    bot = Telegram("secret", "123", session, sleep=sleep, clock=lambda: 100)
    bot.send("hello")
    assert session.post.call_count == 2
    assert any(call.args == (7.0,) for call in sleep.call_args_list)
    assert session.post.call_args.kwargs["json"]["parse_mode"] == "HTML"


def test_max_three_attempts_and_safe_error():
    session, sleep = Mock(), Mock()
    session.post.side_effect = requests.ConnectionError("https://api.telegram.org/botSECRET/sendMessage")
    with pytest.raises(AlertError, match="3 attempts") as exc:
        Telegram("SECRET", "123", session, sleep=sleep).send("hello")
    assert "SECRET" not in str(exc.value)
    assert session.post.call_count == 3
    assert any(call.args == (1.0,) for call in sleep.call_args_list)
    assert any(call.args == (2.0,) for call in sleep.call_args_list)


def test_permanent_error_no_retry():
    session = Mock()
    session.post.return_value = response(403, {"ok": False})
    with pytest.raises(AlertError, match="rejected"):
        Telegram("secret", "123", session, sleep=Mock()).send("hello")
    assert session.post.call_count == 1


def test_rate_limit_between_messages():
    now = [100.0]
    def sleep(seconds):
        now[0] += seconds
    session = Mock()
    session.post.return_value = response()
    bot = Telegram("secret", "123", session, sleep=sleep, clock=lambda: now[0])
    bot.send("one")
    bot.send("two")
    assert now[0] >= 101.0


def test_format_escapes_and_truncates():
    text = format_post(Post("https://linkedin.com/a?x=1&y=2", author='<Alice & "Bob">', text="<" * 400))
    assert "&lt;Alice &amp; &quot;Bob&quot;&gt;" in text
    assert "x=1&amp;y=2" in text
    assert text.splitlines()[2] == "&lt;" * 300


def test_500_retries():
    session = Mock()
    session.post.side_effect = [response(503, {}), response()]
    Telegram("secret", "123", session, sleep=Mock()).send("hi")
    assert session.post.call_count == 2
