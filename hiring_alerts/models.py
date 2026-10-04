from dataclasses import dataclass


@dataclass(frozen=True)
class Post:
    url: str
    title: str = ""
    author: str = ""
    text: str = ""
    source: str = ""
    published: str = ""


class AlertError(Exception):
    """An operational error with a safe, credential-free message."""
