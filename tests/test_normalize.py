from urllib.parse import quote

import pytest

from hiring_alerts.filters import matches
from hiring_alerts.models import Post
from hiring_alerts.normalize import extract_google_url, normalize_url, strip_html


@pytest.mark.parametrize("key", ["url", "q"])
def test_google_redirect(key):
    target = "https://www.linkedin.com/posts/abc?trk=alert&x=a%2Fb"
    wrapped = f"https://www.google.com/url?rct=j&{key}={quote(target, safe='')}&ct=ga"
    assert extract_google_url(wrapped) == target
    assert extract_google_url(target) == target


def test_html():
    assert strip_html("We <b>are hiring</b> &amp; growing<br>Join&nbsp;us!") == "We are hiring & growing Join us!"
    assert strip_html("<p>Hello</p><p>world</p><script>bad()</script>") == "Hello world"


@pytest.mark.parametrize("url", ["https://linkedin.com.evil.org/post", "https://evil-linkedin.com/post",
                                  "javascript:alert(1)", "https://evil.org/linkedin.com", "https://u:p@linkedin.com/a",
                                  "https://linkedin.com:999/a", "https://[invalid"])
def test_reject_external(url):
    assert normalize_url(url) is None


def test_normalization():
    assert normalize_url("http://WWW.LinkedIn.com/posts/abc/?utm_source=x&trk=y&b=2&a=1#frag") == "https://linkedin.com/posts/abc?a=1&b=2"
    assert normalize_url("https://in.linkedin.com/posts/abc/") == "https://linkedin.com/posts/abc"
    assert normalize_url("https://linkedin.com/jobs/view?id=1") != normalize_url("https://linkedin.com/jobs/view?id=2")


def test_keywords():
    post = Post("https://linkedin.com/a", title="HIRING Python engineers", text="remote")
    assert matches(post, ["hiring", "vacancy"], [])
    assert matches(post, [], [])
    assert not matches(post, ["java"], [])
    assert not matches(post, ["hiring"], ["REMOTE"])
