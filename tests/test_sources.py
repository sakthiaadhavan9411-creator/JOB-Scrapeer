from unittest.mock import Mock

import pytest

from hiring_alerts.models import AlertError
from hiring_alerts.sources.apify import fetch_task, map_item
from hiring_alerts.sources.google_alerts import fetch_feed

FIELDS = {"url_field": "url", "author_field": "author.name", "text_field": "text", "date_field": "date"}
ITEM = {"url": "https://linkedin.com/posts/a", "author": {"name": "Alice"}, "text": "Hiring", "date": None}


def test_mapping_and_missing_field():
    assert map_item(ITEM, FIELDS).author == "Alice"
    with pytest.raises(AlertError, match="missing mapped field 'text'"):
        map_item({k: v for k, v in ITEM.items() if k != "text"}, FIELDS)


def test_apify_poll_and_dataset(monkeypatch):
    session = Mock()
    session.request.side_effect = [Mock(json=lambda: {"data": {"id": "run", "status": "RUNNING"}}),
                                   Mock(json=lambda: {"data": {"id": "run", "status": "SUCCEEDED", "defaultDatasetId": "data"}}),
                                   Mock(json=lambda: [ITEM])]
    monkeypatch.setattr("hiring_alerts.sources.apify.time.sleep", lambda _: None)
    assert len(fetch_task("token", "task", FIELDS, 300, 5, session)) == 1
    assert session.request.call_args_list[0].args[0] == "POST"
    assert session.request.call_args_list[-1].kwargs["params"]["offset"] == 0


def test_apify_failure():
    session = Mock()
    session.request.return_value.json.return_value = {"data": {"id": "run", "status": "FAILED"}}
    with pytest.raises(AlertError, match="did not succeed"):
        fetch_task("token", "task", FIELDS, 300, 5, session)


def test_apify_timeout(monkeypatch):
    session = Mock()
    session.request.return_value.json.return_value = {"data": {"id": "run", "status": "RUNNING"}}
    monkeypatch.setattr("hiring_alerts.sources.apify.time.monotonic", Mock(side_effect=[0, 0, 301]))
    with pytest.raises(AlertError, match="timed out"):
        fetch_task("token", "task", FIELDS, 300, 5, session)


def test_dataset_pagination():
    session = Mock()
    session.request.side_effect = [Mock(json=lambda: {"data": {"id": "run", "status": "SUCCEEDED", "defaultDatasetId": "data"}}),
                                   Mock(json=lambda: [ITEM] * 1000), Mock(json=lambda: [ITEM])]
    assert len(fetch_task("token", "task", FIELDS, 300, 5, session)) == 1001
    assert session.request.call_args.kwargs["params"]["offset"] == 1000


@pytest.mark.parametrize("xml", [b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Hiring</title><link href="https://linkedin.com/posts/a"/><content>Engineer</content><published>2026-01-01</published></entry></feed>',
                                b'<rss version="2.0"><channel><item><title>Hiring</title><link>https://linkedin.com/posts/a</link><description>Engineer</description><pubDate>Thu, 01 Jan 2026 00:00:00 GMT</pubDate></item></channel></rss>'])
def test_atom_and_rss(xml):
    session = Mock()
    session.get.return_value.content = xml
    posts = fetch_feed("https://example.com/rss", session)
    assert posts[0].title == "Hiring" and posts[0].text == "Engineer" and posts[0].published


def test_bad_feed_not_treated_as_empty():
    session = Mock()
    session.get.return_value.content = b"<html>Sign in</html>"
    with pytest.raises(AlertError, match="Invalid Atom/RSS"):
        fetch_feed("https://example.com/rss", session)
