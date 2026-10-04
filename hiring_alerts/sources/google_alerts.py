import feedparser
import requests

from ..models import AlertError, Post


def fetch_feed(url: str, session: requests.Session) -> list[Post]:
    try:
        response = session.get(url, timeout=(10, 30))
        response.raise_for_status()
    except requests.RequestException:
        raise AlertError("RSS request failed; check feed URL and connectivity") from None
    parsed = feedparser.parse(response.content)
    # Do not baseline a partial/malformed feed and silently lose its remaining entries.
    if parsed.bozo or not parsed.version:
        raise AlertError("Invalid Atom/RSS document; source was not initialized")
    posts = []
    for entry in parsed.entries:
        contents = entry.get("content", [])
        posts.append(Post(url=entry.get("link", ""), title=entry.get("title", ""),
                          author=entry.get("author", ""),
                          text=contents[0].get("value", "") if contents else entry.get("summary", ""),
                          source="google_alerts", published=entry.get("published") or entry.get("updated", "")))
    return posts
