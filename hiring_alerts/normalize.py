import html
import re
from dataclasses import replace
from html.parser import HTMLParser
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit

from .models import Post


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in {"br", "p", "div", "li"}:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"p", "div", "li"}:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def strip_html(value: str) -> str:
    parser = _Text()
    parser.feed(value)
    parser.close()
    return " ".join(html.unescape("".join(parser.parts)).split())


def extract_google_url(value: str) -> str:
    value = html.unescape(value.strip())
    try:
        parts = urlsplit(value)
        host = (parts.hostname or "").lower()
        if (host == "google.com" or host.endswith(".google.com")) and parts.path == "/url":
            query = parse_qs(parts.query)
            # parse_qs URL-decodes once; decoding again could corrupt encoded URL paths.
            return (query.get("url") or query.get("q") or [value])[0]
    except ValueError:
        pass
    return value


def normalize_url(value: str) -> str | None:
    try:
        parts = urlsplit(extract_google_url(value))
        host = (parts.hostname or "").lower()
        if parts.scheme.lower() not in {"http", "https"}:
            return None
        if host != "linkedin.com" and not host.endswith(".linkedin.com"):
            return None
        if parts.username or parts.password or parts.port not in {None, 80, 443}:
            return None
        if any(ord(c) < 32 for c in value):
            return None
        tracking = {"trk", "trackingid", "lipi", "licu", "refid", "ref", "originalsubdomain", "midtoken", "midsig", "ebp", "eid"}
        query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                 if k.lower() not in tracking and not k.lower().startswith("utm_")]
        if host in {"www.linkedin.com", "m.linkedin.com"} or re.fullmatch(r"[a-z]{2}\.linkedin\.com", host):
            host = "linkedin.com"
        return urlunsplit(("https", host, parts.path.rstrip("/"), urlencode(sorted(query)), ""))
    except ValueError:
        return None


def normalize_post(post: Post) -> Post | None:
    url = normalize_url(post.url)
    if not url:
        return None
    return replace(post, url=url, title=strip_html(post.title),
                   author=strip_html(post.author), text=strip_html(post.text))
