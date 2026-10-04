from collections.abc import Sequence

from .models import Post


def matches(post: Post, include: Sequence[str], exclude: Sequence[str]) -> bool:
    haystack = " ".join((post.title, post.author, post.text)).casefold()
    return (not include or any(k.casefold() in haystack for k in include)) and not any(
        k.casefold() in haystack for k in exclude
    )
